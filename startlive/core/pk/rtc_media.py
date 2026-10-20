"""Audio/video transport after the server's RTC signaling channel is ready.

Imported only for video PK. Traditional PK has no aiortc/PyAV dependency.
"""
import asyncio
from fractions import Fraction
from time import perf_counter, monotonic_ns

from aiortc import (
    AudioStreamTrack,
    VideoStreamTrack,
    RTCBundlePolicy,
    RTCConfiguration,
    RTCPeerConnection,
    RTCSessionDescription,
    clock,
)
from aiortc.mediastreams import MediaStreamError
from av import AudioFifo, AudioFrame, AudioResampler
from av.video.reformatter import Interpolation, VideoReformatter

from startlive.core.exceptions import PkError
from startlive.core.pk.states.encoder import VideoEncodingConfig
from startlive.core.pk.states.session import MediaPacket
from startlive.core.pk.video_encoder_config import configured_plan, \
    current_video_config
from .output_readiness import require_publication_capture
from .rtc_codecs import enable_av1_publication, set_native_codec_preferences
from .rtc_h264 import source_capability
from .rtc_mute import RtcPublisherMute
from .rtc_relay import prepare_relay
from .rtc_sdp import local_media_fragment, merge_remote_fragment
from .rtc_timing import wait_until
from .rtc_video_negotiation import bind_publication_answer, publication_offer
from .rtc_video_sender import configure_video_sender
from .trace import pk_trace, sdp_for_trace
from .video_frames import packet_frame, reformat_packet


async def _packet(buffer, kind, track):
    try:
        packet = await buffer.wait_for_packet(
            kind, 10, running=lambda: track.readyState == "live")
    except asyncio.TimeoutError:
        raise MediaStreamError("OBS media timed out") from None
    if packet is None:
        raise MediaStreamError
    return packet


class ObsVideoTrack(VideoStreamTrack):
    """Crop owned NV12/BGRA snapshots into the existing I420 encoder contract."""

    def __init__(self, buffer, *, require_negotiation=False, video_config=None):
        super().__init__()
        self.buffer = buffer
        self.video_config = video_config or VideoEncodingConfig()
        self.origin = None
        self.last_pts = -1
        self._next_frame_time = None
        # recv() awaits conversion before the next call, so this context is
        # never used concurrently, even when executor threads change.
        self._reformatter = VideoReformatter()
        self.muted = False
        self.frames_emitted = 0
        self.require_negotiation = require_negotiation
        self.video_limits = None
        self._prefetched = None
        self._adaptation = None

    def stop(self):
        super().stop()
        self.buffer.wake(1)

    async def prepare_video(self):
        self._prefetched = await _packet(self.buffer, 1, self)
        if self.video_config.codec_family == "av1":
            from .rtc_av1 import source_capability as av1_capability
            return av1_capability()
        return source_capability(self._prefetched.width,
                                 self._prefetched.height)

    def bind_video(self, limits):
        self.video_limits = limits

    async def recv(self):
        if self.require_negotiation and self.video_limits is None:
            raise PkError("视频帧尚未绑定服务端编码能力")
        if self._next_frame_time is not None:
            await wait_until(self._next_frame_time)
        # Take the latest capture AFTER waiting, avoiding a stale queued frame.
        if self._prefetched is not None:
            packet = self.buffer.take(1) or self._prefetched
            self._prefetched = None
        else:
            packet = await _packet(self.buffer, 1, self)
        limits = self.video_limits
        if limits is None:
            if self.video_config.codec_family == "av1":
                from .rtc_av1 import source_capability as av1_capability
                limits = av1_capability()
            else:
                limits = source_capability(packet.width, packet.height)
        plan = configured_plan(packet.width, packet.height, limits,
                               self.video_config)
        adaptation = (packet.width, packet.height, plan.width, plan.height,
                      plan.frame_rate)
        if adaptation != self._adaptation:
            self._adaptation = adaptation
            pk_trace("rtc.video.adaptation", source_width=packet.width,
                     source_height=packet.height,
                     width=plan.width, height=plan.height,
                     frame_rate=plan.frame_rate,
                     codec=self.video_config.codec_family,
                     reason="send_limits" if adaptation[:2] != adaptation[
                         2:4] or plan.frame_rate < self.video_config.frame_rate
                     else "source_within_negotiated_limits")
        now = perf_counter()
        interval = 1 / plan.frame_rate
        next_time = (
                        self._next_frame_time if self._next_frame_time is not None else now) + interval
        # Preserve the cadence across small wake-up delays; don't accumulate
        # catch-up frames after encoding or sending stalls for a whole period.
        self._next_frame_time = next_time if next_time > now else now + interval
        # Large pixel conversions must not block RTP/RTCP and 20 ms audio.
        crop = self.buffer.video_crop
        frame = await asyncio.to_thread(self._video_frame, packet, self.muted,
                                        plan,
                                        self.video_config.scale_mode, crop)
        if self.origin is None:
            self.origin = packet.timestamp_ns
        capture_pts = (
                              packet.timestamp_ns - self.origin) * 90000 // 1_000_000_000
        frame.pts = max(0 if self.last_pts < 0 else self.last_pts + (
                90000 + plan.frame_rate - 1) // plan.frame_rate,
                        capture_pts)
        frame.time_base = Fraction(1, 90000)
        self.last_pts = frame.pts
        self.frames_emitted += 1
        return frame

    def _video_frame(self, packet, muted, plan, scale_mode, crop):
        frame = packet_frame(packet,
                             crop.rectangle(packet.width, packet.height))
        frame = reformat_packet(
            self._reformatter, frame, packet,
            width=plan.width,
            height=plan.height,
            format="yuv420p",
            dst_color_range="MPEG",
            interpolation=Interpolation[scale_mode.upper()],
        )
        frame.color_range = 1
        if muted:
            # Modify the owned encoder frame only; preview/OBS retain their
            # original packet. Limited-range I420 black keeps RTP flowing.
            for index, plane in enumerate(frame.planes):
                plane.update(
                    bytes([16 if index == 0 else 128]) * plane.buffer_size)
        return frame


class ObsAudioTrack(AudioStreamTrack):
    """Owned 48 kHz interleaved s16 stereo from the StartLive OBS bridge.

    Contract33 confirms this native capture format, but its 10 ms SDK blocks
    and retained tail are LiveHime latency policy. aiortc needs one 20 ms Opus
    frame per recv(). Preserve OBS timestamps to detect capture gaps locally;
    the native PCM producer has no timestamp argument. Neither path requires
    business Mute HTTP success before accepting audio frames.
    """

    def __init__(self, buffer):
        super().__init__()
        self.buffer = buffer
        self.origin = None
        self.next_pts = 0
        self.fifo = AudioFifo()
        self.muted = False
        self.frames_emitted = 0
        self.nonzero_frames_emitted = 0

    def stop(self):
        super().stop()
        self.buffer.wake(2)

    async def recv(self):
        # OBS normally emits 1024 samples. aiortc treats all encoded payloads
        # from one recv() as one RTP timestamp, so give Opus exactly 20 ms.
        while self.fifo.samples < 960:
            packet = await _packet(self.buffer, 2, self)
            if self.origin is None:
                self.origin = packet.timestamp_ns
            packet_pts = (
                                 packet.timestamp_ns - self.origin) * 48000 // 1_000_000_000
            if abs(packet_pts - (self.next_pts + self.fifo.samples)) > 48:
                # Capture dropped samples: do not splice a partial old frame
                # into new audio or compress the timestamp gap out of the feed.
                self.fifo = AudioFifo()
                self.next_pts = max(self.next_pts, packet_pts)
            incoming = AudioFrame(format="s16", layout="stereo",
                                  samples=packet.frames)
            incoming.planes[0].update(packet.payload)
            incoming.sample_rate = packet.sample_rate
            self.fifo.write(incoming)
        frame = self.fifo.read(960)
        if self.muted:
            frame.planes[0].update(bytes(frame.planes[0].buffer_size))
        frame.pts = self.next_pts
        frame.time_base = Fraction(1, 48000)
        self.next_pts = frame.pts + frame.samples
        self.frames_emitted += 1
        self.nonzero_frames_emitted += int(
            any(memoryview(frame.planes[0])[:frame.samples * 4]))
        return frame


class RtcMediaSession:
    """Publish OBS tracks and subscribe to one peer through verified RPCs.

    Reuse the initial connection's peer connection for all reoffers and media,
    as confirmed in contract-2's rtc-transport-topology.json. The caller supplies
    authenticated signaling and a peer whose publication is already known.
    """

    def __init__(self, signaling, local_buffer, remote_buffer, *,
                 peer_connection=None,
                 configuration=None, owner_active=lambda: True):
        self.signaling = signaling
        self.local_buffer, self.remote_buffer = local_buffer, remote_buffer
        config = configuration or RTCConfiguration(iceServers=[],
                                                   bundlePolicy=RTCBundlePolicy.MAX_BUNDLE)
        self._owns_pc = peer_connection is None
        self.pc = peer_connection or RTCPeerConnection(config)
        # aiortc's SDP serializer drops rtcp-mux when the server omits a=rtcp.
        # Keep each successfully applied raw answer for the next fragment merge.
        self._remote_sdp = None
        self.negotiation_lock = asyncio.Lock()
        self.tracks = []
        self._video_publishers = {}
        self.receivers = set()
        self.failure = None
        self.published = self.subscribed = False
        self.closed = False
        self.owner_active = owner_active
        self.mute = RtcPublisherMute(signaling, ready=self._mute_ready,
                                     apply_local=self._apply_muted)
        self._received = {"audio": asyncio.Event(), "video": asyncio.Event()}
        self._frames_received = {"audio": 0, "video": 0}
        self._expected_media = {"audio", "video"}
        self._monitor_task = None
        self._loop_delays = []
        self.pc.on("track", self._on_track)

    def _trace(self, event, **fields):
        ticket = getattr(self.signaling, "ticket", None) or {}
        pk_trace(event, uid=ticket.get("uid"),
                 channel_id=ticket.get("channel_id"),
                 pc_id=hex(id(self.pc)), **fields)

    def _trace_codecs(self, stage, transceivers):
        try:
            def negotiated_codecs(transceiver):
                publication = self._video_publishers.get(transceiver)
                return publication.codecs if publication is not None else transceiver._codecs

            codecs = [{"mid": item.mid, "kind": item.kind,
                       "direction": item.currentDirection,
                       "codecs": [{"mime_type": codec.mimeType,
                                   "payload_type": codec.payloadType,
                                   "clock_rate": codec.clockRate,
                                   "parameters": dict(codec.parameters)}
                                  for codec in negotiated_codecs(item)]} for
                      item in transceivers]
            self._trace("rtc.media.codecs", stage=stage, negotiated=codecs)
        except Exception:
            pass

    def _video_failed(self, error):
        # Called from the sender's async wrapper on this RTC loop, including
        # errors returned by its encode executor. Normal close must stay quiet.
        if self.closed or self.failure is not None:
            return
        self.failure = error if isinstance(error, PkError) else PkError(
            f"视频编码失败：{error}")
        self._trace("rtc.video.failed", error=self.failure)

    async def _trace_stats(self, stage):
        # Counters only: never record PCM, pixels, tokens or arbitrary provider
        # attributes. Transport totals include SCTP and do not prove RTP receipt.
        try:
            report = await asyncio.wait_for(self.pc.getStats(), 1)
            fields = ("id", "type", "kind", "ssrc", "packetsSent",
                      "packetsReceived",
                      "bytesSent", "bytesReceived", "packetsLost", "jitter",
                      "roundTripTime", "fractionLost", "dtlsState")
            stats = []
            now = clock.current_datetime()
            for item in report.values():
                values = {key: getattr(item, key) for key in fields if
                          hasattr(item, key)}
                # The supported video codecs use 90 kHz, Opus uses 48 kHz.
                rate = {"video": 90000, "audio": 48000}.get(
                    getattr(item, "kind", None))
                if rate is not None and hasattr(item, "jitter"):
                    values["jitter_ms"] = round(item.jitter * 1000 / rate, 3)
                if getattr(item, "roundTripTime", None) is not None:
                    values["round_trip_time_ms"] = round(
                        item.roundTripTime * 1000, 3)
                if item.type == "remote-inbound-rtp":
                    # Remote RR stats are retained between reports. Expose age
                    # so an old RTT/loss sample is not mistaken for a fresh one.
                    values["feedback_age_ms"] = round(
                        max(0, (now - item.timestamp).total_seconds()) * 1000,
                        3)
                    values["fraction_lost_percent"] = round(
                        item.fractionLost * 100 / 256, 3)
                stats.append(values)
            capture = [{"kind": track.kind, "state": track.readyState,
                        "muted": track.muted,
                        "frames_emitted": track.frames_emitted,
                        **({
                               "nonzero_frames_emitted": track.nonzero_frames_emitted}
                           if track.kind == "audio" else {})} for track in
                       self.tracks]
            delays, self._loop_delays = self._loop_delays, []
            self._trace("rtc.media.stats", stage=stage, streams=stats,
                        capture=capture,
                        scheduling={"probe_interval_ms": 100,
                                    "samples": len(delays),
                                    "max_delay_ms": round(
                                        max(delays, default=0) * 1000, 3),
                                    "mean_delay_ms": round(
                                        sum(delays) * 1000 / len(delays),
                                        3) if delays else None,
                                    "over_50ms": sum(
                                        delay >= 0.05 for delay in delays)},
                        decoded_frames=dict(self._frames_received),
                        video_senders=[t.sender._pk_video_pacer.snapshot() for t
                                       in self.pc.getTransceivers()
                                       if getattr(t.sender, "_pk_video_pacer",
                                                  None) is not None])
        except Exception as error:
            # Diagnostics must not replace the original error or prevent Leave.
            self._trace("rtc.media.stats.failed", stage=stage,
                        error_type=type(error).__name__, error=error)

    def _start_monitor(self):
        if self._monitor_task is None:
            self._monitor_task = asyncio.create_task(self._monitor())

    async def _monitor(self):
        from startlive.core import app_state
        report_at = perf_counter() + 5
        while not self.closed:
            deadline = perf_counter() + 0.1
            # Measure event-loop wake-up, independently of video encoding and
            # pacing. Do not create extra executor jobs for diagnostics.
            await asyncio.sleep(0.1)
            self._loop_delays.append(max(0, perf_counter() - deadline))
            for transceiver in self.pc.getTransceivers():
                pacer = getattr(transceiver.sender, "_pk_video_pacer", None)
                if pacer is not None:
                    bitrate = pacer.report()
                    if bitrate is not None:
                        app_state.pk_encoder_runtime.update(
                            sent_bitrate_bps=bitrate)
            if perf_counter() >= report_at:
                await self._trace_stats("periodic")
                self._loop_delays.clear()
                report_at = perf_counter() + 5

    def _on_track(self, track):
        self._trace("rtc.media.track", media=track.kind, track_id=track.id)
        task = asyncio.create_task(self._consume(track))
        self.receivers.add(task)
        task.add_done_callback(self._receiver_done)

    def _receiver_done(self, task):
        self.receivers.discard(task)
        if not task.cancelled():
            error = task.exception()
            if error and not self.closed and self.failure is None:
                self._trace("rtc.media.receive.failed", error=error)
                self.failure = PkError("对方音视频接收已中断")

    async def _consume(self, track):
        resampler = AudioResampler(format="s16", layout="stereo",
                                   rate=48000) if track.kind == "audio" else None
        reformatter = VideoReformatter() if track.kind == "video" else None
        audio_window = perf_counter()
        audio_last = None
        audio_gap = 0.0
        audio_samples = audio_frames = 0
        while True:
            frame = await track.recv()
            if track.kind == "video":
                packet = await asyncio.to_thread(self._video_packet, frame,
                                                 reformatter)
                self.remote_buffer.push(packet)
            else:
                now = perf_counter()
                if audio_last is not None:
                    audio_gap = max(audio_gap, now - audio_last)
                audio_last = now
                audio_frames += 1
                for converted in resampler.resample(frame):
                    audio_samples += converted.samples
                    payload = bytes(converted.planes[0])[:converted.samples * 4]
                    self.remote_buffer.push(
                        MediaPacket(2, monotonic_ns(), sample_rate=48000,
                                    frames=converted.samples, payload=payload))
                elapsed = now - audio_window
                if elapsed >= 5:
                    self._trace("rtc.audio.receive",
                                interval_seconds=round(elapsed, 3),
                                decoded_fps=round(audio_frames / elapsed, 2),
                                media_ms=round(audio_samples / 48, 2),
                                max_gap_ms=round(audio_gap * 1000, 2),
                                playback_queue=self.remote_buffer.audio_snapshot())
                    audio_window, audio_gap = now, 0.0
                    audio_samples = audio_frames = 0
            if not self._received[track.kind].is_set():
                self._trace("rtc.media.first_frame", media=track.kind)
            self._frames_received[track.kind] += 1
            self._received[track.kind].set()

    @staticmethod
    def _video_packet(frame, reformatter):
        frame = reformatter.reformat(frame, format="bgra")
        plane = frame.planes[0]
        raw, width = bytes(plane), frame.width * 4
        payload = raw if plane.line_size == width else b"".join(
            raw[y * plane.line_size:y * plane.line_size + width] for y in
            range(frame.height))
        return MediaPacket(1, monotonic_ns(), frame.width, frame.height,
                           payload=payload)

    async def start(self, peer_search):
        """Convenience path when the owner already verified peer readiness."""
        try:
            await self.publish()
            await self.subscribe(peer_search)
        except BaseException:
            await self.close()
            raise

    def _require_ready(self):
        if self.failure is not None:
            raise self.failure
        if not self.signaling.joined:
            raise PkError("RTC 信令尚未入会")
        if self.pc.remoteDescription is None:
            raise PkError("RTC 初次连接尚未完成")

    def _mute_ready(self):
        return (
                not self.closed and self.published and self.owner_active() is True
                and self.signaling.joined and not getattr(self.signaling,
                                                          "closed", False)
                and self.pc.remoteDescription is not None and self.pc.connectionState == "connected")

    def _published_track(self, media):
        track = next((track for track in self.tracks if
                      track.kind == media and track.readyState == "live"), None)
        if track is None:
            raise PkError("当前未发布此类音视频，无法更改静音状态")
        return track

    def _apply_muted(self, media, muted):
        self._published_track(media).muted = muted
        self._trace("rtc.media.mute.local", media=media, muted=muted)

    def mute_state(self, media):
        return self.mute.state(media)

    async def set_muted(self, media, muted, *, changed=None, signal=True):
        self._published_track(media)
        return await self.mute.set_muted(media, muted, changed=changed,
                                         signal=signal)

    async def update_subscription(self, peer_uid, *, video, audio):
        """Change active receive channels on the negotiated subscription."""
        self._require_ready()
        if not self.subscribed:
            raise PkError("RTC 订阅尚未建立")
        await self.signaling.activate_subscription(peer_uid, video=video,
                                                   audio=audio)
        self._expected_media = {kind for kind, enabled in
                                (("video", video), ("audio", audio)) if enabled}

    async def publish(self, *, video=True, audio=True, audio_muted=False):
        """Publish local OBS media without presuming a remote user is ready."""
        self._trace("rtc.media.publish.start", video=video, audio=audio)
        try:
            async with self.negotiation_lock:
                self._require_ready()
                if self.published:
                    raise PkError("本机音视频已经发布")
                self._start_monitor()
                require_publication_capture(self.local_buffer, video=video,
                                            audio=audio)
                video_config = current_video_config() if video else None
                if video_config is not None:
                    self._trace("rtc.video.bitrate_policy", mode="fixed",
                                requested_bitrate_bps=video_config.bitrate_bps,
                                remb_applied=False)
                if video_config is not None and video_config.codec_family == "av1":
                    enable_av1_publication(self.pc)
                if video_config is not None and video_config.encoder == "auto":
                    # Probing drivers can take seconds. Do it before RTP
                    # publishing, off the RTC event loop rather than on the
                    # first video encode frame.
                    from .video_encoder_backend import available_encoders
                    await asyncio.to_thread(available_encoders)
                self.tracks = ([ObsVideoTrack(self.local_buffer,
                                              require_negotiation=True,
                                              video_config=video_config)] if video else []) + (
                                  [ObsAudioTrack(
                                      self.local_buffer)] if audio else [])
                publishing = []
                for track in self.tracks:
                    if track.kind == "audio":
                        track.muted = audio_muted
                    capability = await track.prepare_video() if track.kind == "video" else None
                    transceiver = self.pc.addTransceiver(track,
                                                         direction="sendonly")
                    set_native_codec_preferences(transceiver, video_config)
                    if track.kind == "video":
                        self._video_publishers[
                            transceiver] = configure_video_sender(
                            transceiver.sender, capability=capability,
                            failed=self._video_failed,
                            video_config=video_config)
                    publishing.append(transceiver)
                prepare_relay(self.pc)
                offer = publication_offer(await self.pc.createOffer(),
                                          self._video_publishers)
                self._trace("rtc.sdp.local.offer", stage="publish",
                            sdp=sdp_for_trace(offer.sdp))
                await self.pc.setLocalDescription(offer)
                fragment = local_media_fragment(self.pc.localDescription.sdp,
                                                [track.mid for track in
                                                 publishing])
                self._trace("rtc.sdp.local.applied", stage="publish",
                            sdp=sdp_for_trace(self.pc.localDescription.sdp),
                            request_fragment=sdp_for_trace(fragment))
                answer = await self.signaling.publish(fragment, video=video,
                                                      audio=audio)
                self._trace("rtc.sdp.remote.fragment", stage="publish",
                            sdp=answer)
                # The native merger may synthesize fallback m-lines. They are
                # not evidence of peer codec support: require real PubResp MIDs.
                bind_publication_answer(answer or "", self._video_publishers)
                answer = merge_remote_fragment(
                    self._remote_sdp or self.pc.remoteDescription.sdp,
                    self.pc.localDescription.sdp, answer)
                self._trace("rtc.sdp.remote.answer", stage="publish",
                            sdp=sdp_for_trace(answer))
                # The existing DTLS connection can start senders during SRD.
                # Bind raw-answer limits before crossing that async boundary.
                await self.pc.setRemoteDescription(
                    RTCSessionDescription(answer, "answer"))
                if self.failure is not None:
                    raise self.failure
                self._remote_sdp = answer
                self.published = True
                self._trace_codecs("publish", publishing)
                self._trace("rtc.media.publish.success", video=video,
                            audio=audio)
        except BaseException as error:
            self._trace("rtc.media.publish.failed", error=error)
            if self.failure is not None and error is not self.failure and isinstance(
                    error, Exception):
                raise self.failure from error
            raise

    async def subscribe(self, peer_search, *, video=True, audio=True):
        """The owner must supply a peer confirmed by business/publication data."""
        self._trace("rtc.media.subscribe.start", peer_search=peer_search,
                    video=video, audio=audio)
        try:
            async with self.negotiation_lock:
                self._require_ready()
                if self.subscribed:
                    raise PkError("已经订阅对方音视频")
                self._start_monitor()
                subscribing = []
                # Contract5: disabled receive kinds create no transceiver. Apart
                # from avoiding unwanted tracks, this avoids a separate inactive
                # ICE transport when publishing and receiving different kinds.
                for kind, enabled in (("video", video), ("audio", audio)):
                    if not enabled:
                        continue
                    transceiver = self.pc.addTransceiver(kind,
                                                         direction="recvonly")
                    set_native_codec_preferences(transceiver)
                    subscribing.append(transceiver)
                prepare_relay(self.pc)
                offer = publication_offer(await self.pc.createOffer(),
                                          self._video_publishers)
                self._trace("rtc.sdp.local.offer", stage="subscribe",
                            sdp=sdp_for_trace(offer.sdp))
                await self.pc.setLocalDescription(offer)
                fragment = local_media_fragment(self.pc.localDescription.sdp,
                                                [track.mid for track in
                                                 subscribing])
                self._trace("rtc.sdp.local.applied", stage="subscribe",
                            sdp=sdp_for_trace(self.pc.localDescription.sdp),
                            request_fragment=sdp_for_trace(fragment))
                answer = await self.signaling.subscribe(peer_search, fragment,
                                                        video=video,
                                                        audio=audio)
                self._trace("rtc.sdp.remote.fragment", stage="subscribe",
                            sdp=answer)
                answer = merge_remote_fragment(
                    self._remote_sdp or self.pc.remoteDescription.sdp,
                    self.pc.localDescription.sdp, answer)
                self._trace("rtc.sdp.remote.answer", stage="subscribe",
                            sdp=sdp_for_trace(answer))
                bind_publication_answer(answer, self._video_publishers)
                await self.pc.setRemoteDescription(
                    RTCSessionDescription(answer, "answer"))
                self._remote_sdp = answer
                self._expected_media = {kind for kind, enabled in
                                        (("video", video), ("audio", audio)) if
                                        enabled}
                # Native subscription completes with ApplySubscribe only after
                # the receive answer is installed. Await its server response;
                # a rejected/absent activation must not report subscription ready.
                self._trace("rtc.media.subscribe.activate",
                            peer_search=peer_search, video=video, audio=audio)
                await self.signaling.activate_subscription(peer_search,
                                                           video=video,
                                                           audio=audio)
                if self.failure is not None:
                    raise self.failure
                self.subscribed = True
                self._trace_codecs("subscribe", subscribing)
                self._trace("rtc.media.subscribe.success",
                            peer_search=peer_search, video=video, audio=audio)
        except BaseException as error:
            self._trace("rtc.media.subscribe.failed", peer_search=peer_search,
                        error=error)
            if self.failure is not None and error is not self.failure and isinstance(
                    error, Exception):
                raise self.failure from error
            raise

    async def wait_for_media(self, timeout=15):
        """Wait for enabled incoming kinds; this does not prove outgoing delivery.

        The owner must not report media receipt for an empty subscription.
        A provider action/queue return cannot satisfy these frame events.
        """
        self._trace("rtc.media.wait", expected=sorted(self._expected_media),
                    timeout=timeout)
        if self.failure is not None:
            raise self.failure
        try:
            await asyncio.wait_for(asyncio.gather(*(
                self._received[kind].wait() for kind in self._expected_media)),
                                   timeout)
        except asyncio.TimeoutError:
            if self.failure is not None:
                raise self.failure
            await self._trace_stats("timeout")
            self._trace("rtc.media.timeout",
                        expected=sorted(self._expected_media),
                        received=[kind for kind, event in self._received.items()
                                  if event.is_set()])
            raise PkError("RTC 已协商，但未收到对方画面或声音") from None
        if self.failure is not None:
            raise self.failure
        await self._trace_stats("ready")
        self._trace("rtc.media.ready", received=sorted(self._expected_media))

    def check_connection(self):
        if self.failure:
            raise self.failure
        if self.published:
            require_publication_capture(self.local_buffer,
                                        video=any(
                                            track.kind == "video" for track in
                                            self.tracks),
                                        audio=any(
                                            track.kind == "audio" for track in
                                            self.tracks))
        if getattr(self.signaling, "closed", False):
            raise PkError("RTC 信令连接已断开")
        if self.pc.connectionState in ("failed", "closed"):
            raise PkError("RTC 媒体连接已断开")

    async def close(self):
        self._trace("rtc.media.close.start", published=self.published,
                    subscribed=self.subscribed,
                    owns_pc=self._owns_pc)
        if self._monitor_task is not None:
            self._monitor_task.cancel()
            await asyncio.gather(self._monitor_task, return_exceptions=True)
            self._monitor_task = None
        if self.published and not self.closed:
            await self._trace_stats("close")
        self.closed = True
        self.mute.close()
        for track in self.tracks:
            track.stop()
        tasks = list(self.receivers)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        # RtcConnection owns a shared PC and must send Leave before closing
        # its signaling transport. Standalone loopback sessions own their PC.
        if self._owns_pc:
            await self.pc.close()
        self.remote_buffer.clear()
        from startlive.core import app_state
        app_state.pk_encoder_runtime.reset()
        self._trace("rtc.media.closed")
