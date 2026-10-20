"""Scoped PK video encoding and RTCP refresh-request compatibility."""
from abc import abstractmethod
from collections import deque
from fractions import Fraction
from math import ceil
from struct import iter_unpack

from aiortc import RTCRtpSender
from aiortc.codecs.base import Encoder
from aiortc.codecs.h264 import H264Encoder
from aiortc.mediastreams import VIDEO_TIME_BASE, convert_timebase
from aiortc.rtp import RtcpPsfbPacket, RTCP_PSFB_FIR, RTCP_PSFB_PLI
from av.codec.codec import UnknownCodecError
from av.error import FFmpegError
from av.video.reformatter import VideoReformatter

from startlive.core.constant.pk_video import MAX_ENCODER_LATENCY_SECONDS
from startlive.core.exceptions import PkError
from startlive.core.pk.states.encoder import VideoEncodingConfig
from startlive.core.pk.states.video_publication import VideoPublication
from startlive.core.pk.video_encoder_config import configured_plan
from .rtc_h264 import source_capability, validate_encoder_sps
from .rtc_video_pacer import configure_video_pacing
from .trace import pk_trace
from .video_encoder_backend import encoder_attempts, make_video_context


# Live output must make progress within a quarter-second of submitted media.
# Scale the frame budget with the negotiated FPS, not one GPU's queue depth.


def encoder_delay_budget(frame_rate):
    return max(1, ceil(frame_rate * MAX_ENCODER_LATENCY_SECONDS))


class PkVideoEncoder(Encoder):
    """Encode the owned sending copy within negotiated codec limits.

    Bitrate is fixed by the session configuration and negotiated codec limits.
    REMB is recorded by the feedback adapter without changing this target.
    """

    @staticmethod
    @abstractmethod
    def _source_capability(width, height):
        """Return codec limits for a source geometry.

        Subclasses must accept both dimensions even when their codec ceiling is
        fixed. Live sending and encoder probing deliberately share this one
        signature; do not hide a missing argument behind defaults.
        """
        pass

    def __init__(self, *, require_negotiation=False, video_config=None,
                 allow_fallback=True, use_codec_defaults=False):
        super().__init__()
        self.codec = None
        self.limits = None
        self.require_negotiation = require_negotiation
        self.video_config = video_config or VideoEncodingConfig()
        self.allow_fallback = allow_fallback
        self.use_codec_defaults = use_codec_defaults
        self._codec_limits = None
        self._active_backend = None
        self._backend_candidates = None
        self._backend_index = 0
        self._fallback_reason = ""
        self.last_refresh = None
        self._bitstream_metadata = None
        self.frames = self.refreshes = 0
        self._submitted = {}
        self._ready = deque()
        self._pending_refresh = None
        self._input_index = 0
        self._output_timestamp = None
        self.ssrc = None
        self._generation = 0
        self._reformatter = VideoReformatter()

    def _discard_codec(self):
        codec, self.codec = self.codec, None
        if codec is not None and self._active_backend == "libsvtav1" and codec.is_open:
            # SVT requires EOS before deinitialization. This is teardown,
            # never a poll for live output; any
            # remaining old-session packets must not reach the new stream.
            try:
                codec.encode(None)
            except FFmpegError:
                pass  # An already failed / drained codec can still be freed.

    def __del__(self):
        # aiortc releases its encoder when the RTP task finishes.
        self._discard_codec()

    @property
    def target_bitrate(self):
        return self.video_config.bitrate_limit(self.limits)

    def bind_video(self, limits):
        if self.limits is not None and self.limits != limits:
            raise PkError("视频发布能力已改变，需要重新建立视频连接")
        self.limits = limits

    def _report_runtime(self, backend):
        from startlive.core import app_state
        app_state.pk_encoder_runtime.update(backend=backend,
                                            fallback_reason=self._fallback_reason)

    def _start_codec(self, name, frame, plan, limits):
        codec = make_video_context(name, frame.width, frame.height,
                                   plan.frame_rate,
                                   self.target_bitrate, limits,
                                   self.video_config,
                                   use_codec_defaults=self.use_codec_defaults,
                                   colorspace=frame.colorspace,
                                   color_range=frame.color_range)
        self.codec = codec
        self._active_backend = name
        self._codec_limits = limits
        self.last_refresh = None
        self._bitstream_metadata = None
        self._submitted.clear()
        self._ready.clear()
        self._pending_refresh = None
        self._input_index = 0
        self._output_timestamp = None
        self._generation += 1
        self._report_runtime(name)
        pk_trace("rtc.video.encoder", ssrc=self.ssrc,
                 generation=self._generation,
                 codec=name, width=frame.width, height=frame.height,
                 bitrate=self.target_bitrate, frame_rate=plan.frame_rate,
                 requested_max_bitrate_bps=self.video_config.bitrate_bps,
                 codec_parameters=self._parameters(limits),
                 rate_control=self.video_config.rate_control,
                 scale_mode=self.video_config.scale_mode,
                 refresh_seconds=self.video_config.keyframe_interval,
                 resolution_policy="fixed_target_and_negotiated_limits")

    def _encode_using_backend(self, name, frame, refresh, plan, limits):
        if self.codec is None:
            self._start_codec(name, frame, plan, limits)
            refresh = "encoder_start" if self._generation == 1 else "encoder_restart"
        # Some backends accept only NV12 rather than I420 software frames.
        converted = frame
        if frame.format.name != self.codec.pix_fmt:
            converted = self._reformatter.reformat(frame,
                                                   format=self.codec.pix_fmt)
            converted.pts, converted.time_base = frame.pts, frame.time_base
        from av.video.frame import PictureType

        # Match returned packets to submitted frames in the codec time base.
        # FFmpeg rescales with AV_ROUND_NEAR_INF (ties away from zero).
        ticks = Fraction(frame.pts) * frame.time_base / self.codec.time_base
        pts = int(abs(ticks) + Fraction(1, 2)) * (-1 if ticks < 0 else 1)
        if pts in self._submitted:
            raise PkError("Video encoder received a duplicate input timestamp")
        requested = refresh if self._pending_refresh is None else None
        if requested:
            self._pending_refresh = pts
        timestamp = convert_timebase(frame.pts, frame.time_base,
                                     VIDEO_TIME_BASE)
        self._submitted[pts] = (self._input_index, timestamp, requested)
        self._input_index += 1
        converted.pict_type = PictureType.I if requested else PictureType.NONE

        # encode(None) signals end-of-stream; it must never be used to poll a
        # live encoder. Empty output is normal while native buffers fill.
        packets = self.codec.encode(converted)
        groups = []
        for packet in packets:
            if packet.pts is None or packet.time_base is None:
                raise PkError(
                    "Video output packet has no presentation timestamp")
            key = Fraction(packet.pts) * packet.time_base / self.codec.time_base
            if groups and groups[-1][0] == key:
                groups[-1][1].extend(bytes(packet))
                groups[-1][2] |= packet.is_keyframe
            else:
                groups.append(
                    [key, bytearray(bytes(packet)), packet.is_keyframe])
        for key, data, keyframe in groups:
            # No B frames are allowed: output must preserve input order.
            if not self._submitted or key != next(iter(self._submitted)):
                raise PkError("Video output timestamp is unknown or reordered")
            _, output_timestamp, needs_refresh = self._submitted.pop(key)
            units, refreshed = self._split_picture(bytes(data), keyframe, frame,
                                                   plan, limits)
            if needs_refresh and not refreshed:
                raise PkError(
                    "PK video encoder did not produce the requested refresh frame")
            if needs_refresh:
                self._pending_refresh = None
            if refreshed:
                self.last_refresh = output_timestamp * VIDEO_TIME_BASE
                self.refreshes += 1
                pk_trace("rtc.video.keyframe", ssrc=self.ssrc,
                         codec=name, generation=self._generation,
                         media_timestamp=output_timestamp,
                         encoded_bytes=len(data),
                         reason=needs_refresh or "encoder",
                         target_bitrate_bps=self.target_bitrate,
                         encoder_bitrate_bps=self.codec.bit_rate,
                         width=frame.width, height=frame.height)
            self._ready.append((units, output_timestamp))

        if self._submitted:
            oldest_index = next(iter(self._submitted.values()))[0]
            budget = encoder_delay_budget(plan.frame_rate)
            if self._input_index - oldest_index > budget:
                raise PkError(
                    f"Video encoder stalled: no output for input {oldest_index} "
                    f"after {budget} subsequent frames at {plan.frame_rate} FPS")
        if len(self._ready) > encoder_delay_budget(plan.frame_rate):
            raise PkError("Video output queue exceeded live latency budget")
        if self._ready:
            units, self._output_timestamp = self._ready.popleft()
            return units
        self._output_timestamp = None
        return []

    def encode(self, frame, force_keyframe=False):
        # aiortc's base implementation stamps packets with the CURRENT input
        # frame, which is incorrect when a hardware encoder returns older AUs.
        units = self._encode_frame(frame, force_keyframe)
        timestamp = self._output_timestamp
        if timestamp is None:
            timestamp = convert_timebase(frame.pts, frame.time_base,
                                         VIDEO_TIME_BASE)
        return self._packetize(units), timestamp

    def _encode_frame(self, frame, force_keyframe):
        if self.require_negotiation and self.limits is None:
            raise PkError("视频尚未完成编码能力协商")
        limits = self.limits or self._source_capability(frame.width,
                                                        frame.height)
        plan = configured_plan(frame.width, frame.height, limits,
                               self.video_config)
        if (plan.width, plan.height) != (frame.width, frame.height):
            raise PkError("发送视频尺寸超出已协商的编码能力")
        if self.codec and (
                self.codec.width != frame.width or self.codec.height != frame.height
                or self._codec_limits != limits or self.codec.framerate != plan.frame_rate
                or self.codec.colorspace != frame.colorspace or self.codec.color_range != frame.color_range):
            self._discard_codec()
        stamp = frame.pts * frame.time_base
        interval = self.video_config.keyframe_interval
        refresh = ("feedback" if force_keyframe else
                   "interval" if self.last_refresh is None or stamp - self.last_refresh >= interval else None)
        if self._backend_candidates is None:
            self._backend_candidates = encoder_attempts(
                self.video_config.encoder)
        while True:
            backend = self._backend_candidates[self._backend_index]
            try:
                units = self._encode_using_backend(backend, frame, refresh,
                                                   plan, limits)
                break
            except (FFmpegError, UnknownCodecError, PkError) as error:
                if not self.allow_fallback or self._backend_index + 1 == len(
                        self._backend_candidates):
                    raise
                # Advance only on a codec/bitstream failure, never on arbitrary
                # programming errors. A failed candidate stays retired for
                # this sender, including subsequent bitrate reconfiguration.
                self._backend_index += 1
                self._fallback_reason = f"{backend} 编码失败 ({type(error).__name__})"
                pk_trace("rtc.video.encoder_fallback", backend=backend,
                         reason=type(error).__name__, detail=str(error),
                         submitted_frames=self._input_index,
                         pending_frames=len(self._submitted),
                         pending_refresh=self._pending_refresh,
                         to=self._backend_candidates[self._backend_index])
                self._discard_codec()
                refresh = "encoder_restart"
        self.frames += 1
        return units

    def pack(self, packet):
        raise PkError("PK 视频发送只接受原始视频帧")


class PkH264Encoder(PkVideoEncoder):
    @staticmethod
    def _source_capability(width, height):
        return source_capability(width, height)

    _packetize = staticmethod(H264Encoder._packetize)
    _split_bitstream = staticmethod(H264Encoder._split_bitstream)

    @staticmethod
    def _parameters(limits):
        return {"profile-level-id": limits.profile_level_id}

    def _split_picture(self, data, _, frame, plan, limits):
        # _ is the keyframe packet hint; H264 refresh is authoritative only when
        # the bitstream contains an IDR (type 5). Keep the shared five-argument
        # signature used by the AV1 encoder and the caller.
        if not data.startswith((b"\x00\x00\x01", b"\x00\x00\x00\x01")):
            raise PkError("H264 output is not Annex-B")
        nals = list(self._split_bitstream(data))
        if not nals or any(
                nal[0] & 128 or not 1 <= nal[0] & 31 <= 23 for nal in nals):
            raise PkError("H264 output contains invalid NAL units")
        types = {nal[0] & 31 for nal in nals}
        for nal in nals:
            if nal[0] & 31 == 7:
                _, references = validate_encoder_sps(
                    nal, frame.width, frame.height, plan.frame_rate, limits)
                metadata = (frame.width, frame.height, nal[1], nal[2], nal[3],
                            references)
                if metadata != self._bitstream_metadata:
                    self._bitstream_metadata = metadata
                    pk_trace("rtc.video.bitstream", codec=self._active_backend,
                             width=frame.width, height=frame.height,
                             profile_idc=nal[1], profile_iop=nal[2],
                             level_idc=nal[3],
                             profile_level_id=nal[1:4].hex(),
                             reference_frames=references)
        if not types.intersection({1, 5}):
            raise PkError("H264 output contains no picture")
        if 5 in types and not {7, 8}.issubset(types):
            raise PkError("PK H264 refresh is missing SPS/PPS")
        return nals, 5 in types


class PkAv1Encoder(PkVideoEncoder):
    @staticmethod
    def _source_capability(width, height):
        # AV1's sender ceiling is a fixed level, independent of source size.
        # Keep the shared parameter names so keyword callers stay compatible;
        # the live/probe paths intentionally still pass both dimensions.
        del width, height
        from .rtc_av1 import source_capability
        return source_capability()

    @staticmethod
    def _parameters(limits):
        return limits.parameters

    @staticmethod
    def _packetize(obus):
        from .rtc_av1 import packetize
        return packetize(obus)

    def _split_picture(self, data, keyframe, frame, plan, limits):
        from .rtc_av1 import split_obus, validate_obus
        obus = split_obus(data)
        metadata = validate_obus(obus, frame.width, frame.height,
                                 plan.frame_rate, limits)
        if keyframe and (not obus or (obus[0][0] >> 3) & 15 != 1):
            raise PkError("AV1 关键帧缺少序列头，无法独立解码")
        if metadata is not None and metadata != self._bitstream_metadata:
            self._bitstream_metadata = metadata
            level, tier, width, height = metadata
            pk_trace("rtc.video.bitstream", codec=self._active_backend,
                     width=width, height=height, level_idx=level, tier=tier,
                     profile=0)
        return obus, keyframe


def configure_video_sender(sender, *, capability=None, failed=None,
                           video_config=None):
    if not isinstance(sender, RTCRtpSender):
        return
    if sender.kind != "video" or sender._RTCRtpSender__encoder is not None:
        return
    config = video_config or VideoEncodingConfig()
    encoder_type = PkAv1Encoder if config.codec_family == "av1" else PkH264Encoder
    encoder = encoder_type(require_negotiation=capability is not None,
                           video_config=config)
    encoder.ssrc = sender._ssrc
    sender._RTCRtpSender__encoder = encoder
    publication = VideoPublication(capability,
                                   config) if capability is not None else None
    if publication is not None:
        original_send = sender.send
        original_next_frame = sender._next_encoded_frame

        async def send(parameters):
            if sender._RTCRtpSender__started:
                # A Sub reoffer re-enters send(). aiortc does not reconfigure
                # an active sender; neither should this scoped first-bind hook.
                return await original_send(parameters)
            try:
                await original_send(publication.sender_parameters(parameters))
            except Exception as error:
                if failed is not None:
                    failed(error)
                raise

        async def next_frame(codec):
            try:
                return await original_next_frame(codec)
            except Exception as error:
                # The executor's encode exception is back on the RTC loop here.
                # aiortc otherwise logs it and silently retires the sender.
                if failed is not None:
                    failed(error)
                raise

        sender.send = send
        sender._next_encoded_frame = next_frame
    configure_video_pacing(sender)
    configure_refresh_requests(sender.transport)
    return publication


def configure_refresh_requests(transport):
    router = transport._rtp_router
    if getattr(router, "_pk_refresh_compat", False):
        return
    original = router.route_rtcp
    fir_sequences = {}

    def route(packet):
        recipients = original(packet)
        if isinstance(packet, RtcpPsfbPacket) and packet.fmt == RTCP_PSFB_FIR:
            # RFC5104 4.3.1.2: FIR media_ssrc is zero; targets are in FCI.
            # aiortc 1.15 routes only media_ssrc, losing valid FIR requests.
            recipients = set()
            if packet.fci and len(packet.fci) % 8 == 0:
                for target, seq in iter_unpack("!IB3x", packet.fci):
                    recipient = router.senders.get(target)
                    if recipient is None or recipient.kind != "video":
                        continue
                    key = (packet.ssrc, target)
                    if fir_sequences.get(key) == seq:
                        continue
                    if len(fir_sequences) >= 128:
                        fir_sequences.clear()
                    fir_sequences[key] = seq
                    recipients.add(recipient)
        if isinstance(packet, RtcpPsfbPacket) and packet.fmt in (RTCP_PSFB_FIR,
                                                                 RTCP_PSFB_PLI):
            pk_trace("rtc.video.refresh_request",
                     kind="fir" if packet.fmt == RTCP_PSFB_FIR else "pli",
                     recipients=len(recipients),
                     ssrcs=sorted(item._ssrc for item in recipients))
        return recipients

    router.route_rtcp = route
    router._pk_refresh_compat = True
