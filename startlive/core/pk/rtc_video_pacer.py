"""Per-PK video pacing; audio, RTCP and repairs use the existing fast path.

aiortc sends an entire encoded frame without rate pacing. Bound short bursts
instead of dropping RTP fragments or growing another queue. Waiting happens
only in the video sender coroutine, before encryption; the latest-frame OBS
buffer already bounds producer backlog. The 2.5x rate is StartLive policy.
"""
from startlive.core.constant.pk_video import (
    PK_PACER_BURST_BYTES,
    PK_PACER_REFILL_SECONDS,
    PK_PACER_RATE_FACTOR,
)
from contextvars import ContextVar
from time import perf_counter

from aiortc import clock
from aiortc.rtcrtpsender import RTP_HISTORY_SIZE
from aiortc.rtp import (
    RtpPacket,
    RtcpRtpfbPacket,
    RtcpPsfbPacket,
    RTCP_RTPFB_NACK,
    RTCP_PSFB_APP,
    is_rtcp,
    unpack_remb_fci,
)

from .rtc_timing import wait_until
from .trace import pk_trace
from startlive.core.constant.pk_video_config import DEFAULT_VIDEO_CONFIG


class PkVideoPacer:
    BURST_BYTES = PK_PACER_BURST_BYTES
    REFILL_SECONDS = PK_PACER_REFILL_SECONDS
    RATE_FACTOR = PK_PACER_RATE_FACTOR

    def __init__(self, sender):
        self.sender = sender
        self.credit = float(self.BURST_BYTES)
        self.updated = perf_counter()
        self.packets = self.bytes = self.waits = 0
        self.frames = 0
        self.wait_seconds = self.max_wait_late_ms = 0.0
        self.nack_packets = self.nack_missing = self.nack_refreshes = 0
        self.max_frame_bytes = self.max_frame_packets = 0
        self.frame_bytes = self.frame_packets = 0
        self.frame_timestamp = None
        self.last_trace = self.updated
        self.last_recovery = 0.0
        self._window_bytes = self._window_frames = self._window_capture = 0
        self._window_wait = 0.0

    async def wait(self, size):
        waited = False
        while True:
            now = perf_counter()
            encoder = self.sender._RTCRtpSender__encoder
            rate = max(1, getattr(encoder, "target_bitrate",
                                  DEFAULT_VIDEO_CONFIG.bitrate_bps)) * self.RATE_FACTOR / 8
            self.credit = min(max(self.BURST_BYTES, size),
                              self.credit + (now - self.updated) * rate)
            self.updated = now
            if self.credit >= size:
                self.credit -= size
                return waited
            self.waits += 1
            waited = True
            # Refill a small batch instead of scheduling a thread for every
            # sub-millisecond packet gap. The existing burst cap still applies.
            refill = max(size,
                         min(self.BURST_BYTES, rate * self.REFILL_SECONDS))
            deadline = now + (refill - self.credit) / rate
            await wait_until(deadline)
            end = perf_counter()
            self.wait_seconds += end - now
            self.max_wait_late_ms = max(self.max_wait_late_ms,
                                        max(0, end - deadline) * 1000)

    def observed(self, data):
        stamp = int.from_bytes(data[4:8], "big")
        if stamp != self.frame_timestamp:
            self.frame_timestamp = stamp
            self.frame_bytes = self.frame_packets = 0
        self.frame_bytes += len(data)
        self.frame_packets += 1
        self.max_frame_bytes = max(self.max_frame_bytes, self.frame_bytes)
        self.max_frame_packets = max(self.max_frame_packets, self.frame_packets)
        self.packets += 1
        self.bytes += len(data)
        if data[1] & 0x80:
            self.frames += 1

    def report(self):
        """Sample on the session timer so an idle sender also reports zero."""
        now = perf_counter()
        elapsed = now - self.last_trace
        if elapsed >= 1:
            encoder = self.sender._RTCRtpSender__encoder
            capture = getattr(self.sender.track, "frames_emitted", 0)
            bitrate = round((self.bytes - self._window_bytes) * 8 / elapsed)
            pk_trace("rtc.video.send", ssrc=self.sender._ssrc,
                     interval_seconds=round(elapsed, 3),
                     sent_fps=round(
                         (self.frames - self._window_frames) / elapsed, 2),
                     encoder_input_fps=round(
                         (capture - self._window_capture) / elapsed, 2),
                     rtp_bitrate_bps=bitrate,
                     target_bitrate_bps=getattr(encoder, "target_bitrate",
                                                None),
                     encoder_bitrate_bps=getattr(
                         getattr(encoder, "codec", None), "bit_rate", None),
                     pacing_wait_ms=round(
                         (self.wait_seconds - self._window_wait) * 1000, 2),
                     max_wait_late_ms=round(self.max_wait_late_ms, 2),
                     **self.snapshot())
            self.last_trace = now
            self._window_bytes, self._window_frames = self.bytes, self.frames
            self._window_capture, self._window_wait = capture, self.wait_seconds
            self.max_wait_late_ms = 0.0
            return bitrate

    def snapshot(self):
        return {key: getattr(self, key) for key in (
            "packets", "bytes", "frames", "waits", "max_frame_bytes",
            "max_frame_packets",
            "nack_packets", "nack_missing", "nack_refreshes")}


def configure_video_pacing(sender):
    if getattr(sender, "_pk_video_pacer", None) is not None:
        return
    pacer = sender._pk_video_pacer = PkVideoPacer(sender)
    transport = sender.transport
    original_send = transport._send_rtp
    retransmitting = ContextVar("pk_video_retransmitting", default=False)

    original_retransmit = sender._retransmit

    async def retransmit(sequence_number):
        # RTX is optional: aiortc repairs on the primary SSRC when it was not
        # negotiated. Scope the bypass to this repair coroutine so concurrent
        # original video packets still wait for their normal pacing credit.
        token = retransmitting.set(True)
        try:
            await original_retransmit(sequence_number)
        finally:
            retransmitting.reset(token)

    sender._retransmit = retransmit

    async def send(data):
        if (len(data) >= 12 and not is_rtcp(data)
                and int.from_bytes(data[8:12], "big") == sender._ssrc
                and not retransmitting.get()):
            waited = await pacer.wait(len(data))
            if waited:
                # abs-send-time was stamped before the wait in aiortc. Keep
                # bandwidth feedback tied to actual transmission, not enqueue.
                extensions = sender._RTCRtpSender__rtp_header_extensions_map
                packet = RtpPacket.parse(data, extensions)
                if packet.extensions.abs_send_time is not None:
                    packet.extensions.abs_send_time = (
                                                                  clock.current_ntp_time() >> 14) & 0xFFFFFF
                    data = packet.serialize(extensions)
            await original_send(data)
            pacer.observed(data)
        else:
            await original_send(data)

    transport._send_rtp = send
    original_feedback = sender._handle_rtcp_packet

    async def feedback(packet):
        remb = None
        encoder = sender._RTCRtpSender__encoder
        before = getattr(encoder, "target_bitrate", None)
        if isinstance(packet, RtcpPsfbPacket) and packet.fmt == RTCP_PSFB_APP:
            try:
                bitrate, ssrcs = unpack_remb_fci(packet.fci)
                if sender._ssrc in ssrcs:
                    remb = bitrate
            except ValueError:
                pass  # aiortc also ignores malformed / non-REMB feedback.
        if isinstance(packet,
                      RtcpRtpfbPacket) and packet.fmt == RTCP_RTPFB_NACK:
            history = sender._RTCRtpSender__rtp_history
            missing = sum(1 for seq in packet.lost
                          if (cached := history.get(
                seq % RTP_HISTORY_SIZE)) is None or cached.sequence_number != seq)
            pacer.nack_packets += len(packet.lost)
            pacer.nack_missing += missing
            now = perf_counter()
            if missing and now - pacer.last_recovery >= 0.5:
                # Sending an incomplete delta chain cannot repair a lost
                # reference. Request one complete picture when cache expired.
                pacer.last_recovery = now
                pacer.nack_refreshes += 1
                sender._send_keyframe()
        if remb is not None:
            pk_trace("rtc.video.remb", ssrc=sender._ssrc,
                     receiver_bitrate_bps=remb,
                     previous_target_bps=before,
                     target_bitrate_bps=getattr(encoder, "target_bitrate",
                                                None),
                     encoder_bitrate_bps=getattr(
                         getattr(encoder, "codec", None), "bit_rate", None),
                     applied=False, policy="fixed")
            # Only this sender's REMB is diagnostic-only. Keep RR, NACK,
            # PLI/FIR and other feedback on aiortc's existing handling path.
            return
        await original_feedback(packet)

    sender._handle_rtcp_packet = feedback
    pk_trace("rtc.video.pacing", ssrc=sender._ssrc,
             burst_bytes=pacer.BURST_BYTES,
             rate_factor=pacer.RATE_FACTOR,
             refill_ms=pacer.REFILL_SECONDS * 1000)
