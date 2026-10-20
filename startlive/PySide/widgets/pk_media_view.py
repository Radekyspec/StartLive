from concurrent.futures import ThreadPoolExecutor
from math import ceil
from threading import local
from time import monotonic, perf_counter

from PySide6.QtCore import QEvent, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QImage, QPainter
from PySide6.QtMultimedia import QAudioFormat, QAudioSink, QMediaDevices, \
    QtAudio
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from startlive.core.constant.pk_media import PK_VIEW_AUDIO_BYTES_PER_SECOND, \
    PK_VIEW_AUDIO_PREFILL_BYTES
from startlive.core.pk.trace import pk_trace

_preview_context = local()


class VideoSurface(QLabel):
    """Paint directly from the source rectangle, without intermediate rasters."""

    def __init__(self, text):
        super().__init__(text)
        self._frame = None
        self._source = None

    def set_frame(self, image, source):
        self._frame, self._source = image, source
        self.update()

    def paintEvent(self, event):
        if self._frame is None:
            super().paintEvent(event)
            return
        painter = QPainter(self)
        painter.fillRect(self.rect(), Qt.GlobalColor.black)
        source = self._source
        bounds = QRectF(self.contentsRect())
        scale = min(bounds.width() / source.width(),
                    bounds.height() / source.height())
        target = QRectF(0, 0, source.width() * scale, source.height() * scale)
        target.moveCenter(bounds.center())
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.drawImage(target, self._frame, source)


class PkMediaView(QWidget):
    imageChanged = Signal(object)
    _previewReady = Signal(object, int)
    AUDIO_BYTES_PER_SECOND = PK_VIEW_AUDIO_BYTES_PER_SECOND
    AUDIO_PREFILL_BYTES = PK_VIEW_AUDIO_PREFILL_BYTES

    def __init__(self, parent=None, *, title):
        super().__init__(parent)
        self.title = QLabel(title)
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.video = VideoSurface("等待画面")
        self.video.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.video.setFixedSize(600, 480)
        self.video.setStyleSheet("background: #16181d; color: #b0b4be")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(self.title)
        layout.addWidget(self.video, 1, Qt.AlignmentFlag.AlignHCenter)
        self.audio_status = QLabel()
        self.audio_status.setTextFormat(Qt.TextFormat.PlainText)
        self.audio_status.setWordWrap(True)
        self.audio_status.setFixedHeight(self.fontMetrics().lineSpacing() * 2)
        self.audio_status.hide()
        layout.addWidget(self.audio_status)
        self._image = None
        self._image_is_cropped = False
        self._preview_packet = None
        self._preview_executor = None
        self._preview_busy = False
        self._preview_generation = 0
        self._previewReady.connect(self._apply_preview)
        self._crop = None
        self.video.installEventFilter(self)
        self._sink = None
        self._device = None
        self._muted = True
        self._audio_retry_at = 0.0
        self._pending_audio = bytearray()
        self._audio_buffering = True
        self._audio_running = False
        self._audio_underruns = self._audio_dropped_bytes = 0
        self._audio_stats_at = perf_counter()
        self._audio_last_feed = None
        self._audio_max_feed_gap = 0.0
        self._audio_timer = QTimer(self)
        self._audio_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._audio_timer.setInterval(10)
        self._audio_timer.timeout.connect(self._drain_audio)

    def set_muted(self, muted):
        self._muted = muted
        if muted:
            self._release_audio()
            self._audio_status("")
        # An explicit unmute may immediately retry a newly available output.
        self._audio_retry_at = 0.0

    def show_packet(self, packet):
        if packet.kind == 1:
            if packet.pixel_format == "nv12":
                # Retain only the latest packet; its lease pins the pooled buffer.
                self._preview_packet = packet
                self._request_preview()
                return
            self._preview_packet = None
            self._preview_generation += 1
            self._image_is_cropped = False
            self._image = QImage(packet.payload, packet.width, packet.height,
                                 packet.width * 4,
                                 QImage.Format.Format_ARGB32).copy()
            self.imageChanged.emit(self._image)
            self._render()
        elif not self._muted:
            self._play_audio(packet.payload)

    def _request_preview(self):
        packet = self._preview_packet
        if packet is None or self._preview_busy or not self.isVisible():
            return
        # Read QWidget geometry on the GUI thread. Workers receive only values.
        bounds = self.video.contentsRect()
        dpr = self.video.devicePixelRatioF()
        pixels = (max(1, ceil(bounds.width() * dpr)),
                  max(1, ceil(bounds.height() * dpr)))
        rectangle = self._crop.rectangle(packet.width,
                                         packet.height) if self._crop else None
        if self._preview_executor is None:
            executor = self._preview_executor = ThreadPoolExecutor(
                max_workers=1, thread_name_prefix="PK-preview")
            self.destroyed.connect(
                lambda: executor.shutdown(wait=False, cancel_futures=True))
        self._preview_busy = True
        generation = self._preview_generation
        future = self._preview_executor.submit(self._convert_preview, packet,
                                               rectangle, pixels)

        def done(result):
            try:
                images = result.result()
            except Exception as error:
                pk_trace("video.preview.failed", error=error)
                images = None
            try:
                self._previewReady.emit(images, generation)
            except RuntimeError:
                pass  # Widget already destroyed; no native memory is borrowed.

        future.add_done_callback(done)

    @staticmethod
    def _convert_preview(packet, rectangle, pixels):
        from av.video.reformatter import Interpolation, VideoReformatter
        from startlive.core.pk.video_frames import packet_frame, reformat_packet
        if not hasattr(_preview_context, "reformatters"):
            _preview_context.reformatters = (VideoReformatter(),
                                             VideoReformatter())

        def convert(frame, bounds, reformatter, interpolation):
            scale = min(1, bounds[0] / frame.width, bounds[1] / frame.height)
            frame = reformat_packet(reformatter, frame, packet,
                                    width=max(1, round(frame.width * scale)),
                                    height=max(1, round(frame.height * scale)),
                                    format="bgra", dst_color_range="JPEG",
                                    interpolation=interpolation)
            return QImage(memoryview(frame.planes[0]), frame.width,
                          frame.height,
                          frame.planes[0].line_size,
                          QImage.Format.Format_ARGB32).copy()

        # Main preview crops original pixels BEFORE scaling to physical pixels.
        image = convert(packet_frame(packet, rectangle), pixels,
                        _preview_context.reformatters[0], Interpolation.LANCZOS)
        # The crop selector needs the entire source, not the main preview aperture.
        thumbnail = (convert(packet_frame(packet), (960, 768),
                             _preview_context.reformatters[1],
                             Interpolation.BILINEAR)
                     if rectangle is not None else image.copy())
        thumbnail.setText("source_width", str(packet.width))
        thumbnail.setText("source_height", str(packet.height))
        return image, thumbnail

    def _apply_preview(self, images, generation):
        self._preview_busy = False
        if generation != self._preview_generation:
            self._request_preview()
            return
        if images is None:
            return
        self._image, thumbnail = images
        self._image_is_cropped = True
        self.imageChanged.emit(thumbnail)
        self._render()

    def set_crop(self, crop):
        if crop == self._crop:
            return
        self._crop = crop
        self._invalidate_preview()
        self._render()

    def _invalidate_preview(self):
        self._preview_generation += 1
        self._request_preview()

    def eventFilter(self, watched, event):
        if watched is self.video and event.type() in (
                QEvent.Type.Resize, QEvent.Type.DevicePixelRatioChange,
                QEvent.Type.Show):
            self._invalidate_preview()
        return super().eventFilter(watched, event)

    def _render(self):
        if self._image is None:
            self.video.set_frame(None, None)
            return
        source = QRectF(self._image.rect())
        if self._crop is not None and not self._image_is_cropped:
            width = int(self._image.text("source_width") or self._image.width())
            height = int(
                self._image.text("source_height") or self._image.height())
            x, y, w, h = self._crop.rectangle(width, height)
            sx, sy = self._image.width() / width, self._image.height() / height
            source = QRectF(x * sx, y * sy, w * sx, h * sy)
        self.video.set_frame(self._image, source)

    def _play_audio(self, pcm):
        if self._sink is None:
            if monotonic() < self._audio_retry_at:
                return
            audio = QAudioFormat()
            audio.setSampleRate(48000)
            audio.setChannelCount(2)
            audio.setSampleFormat(QAudioFormat.SampleFormat.Int16)
            output = QMediaDevices.defaultAudioOutput()
            if output.isNull():
                self._audio_failed(
                    "已收到声音，但本机没有可用的默认音频输出；将自动重试")
                return
            if not output.isFormatSupported(audio):
                self._audio_failed(
                    "已收到声音，但默认输出不支持 48 kHz 双声道 16 位播放；将自动重试")
                return
            try:
                sink = self._sink = QAudioSink(output, audio, self)
                # Some PySide builds expose the signal as QAudio::State but
                # cannot convert that legacy enum argument to Python. A
                # zero-argument callback reads the supported state() result.
                sink.stateChanged.connect(
                    lambda: self._audio_state_changed(sink))
                sink.setBufferSize(19200)  # 100 ms of stereo s16le
                device = sink.start()
                if sink is not self._sink:  # A synchronous error signal retired it.
                    return
                self._device = device
                if device is None:
                    self._audio_failed(
                        "已收到声音，但无法启动本机音频播放；将自动重试")
                    return
                pk_trace("audio.playback.started", view=self.title.text(),
                         sample_rate=48000,
                         channels=2, sample_format="s16")
            except (RuntimeError, OSError):
                self._audio_failed(
                    "已收到声音，但无法启动本机音频播放；将自动重试")
                return
        self._audio_state_changed(self._sink)
        if self._sink is None:
            return
        # Preserve partial writes and retry without waiting for another frame.
        # Bound latency to 200 ms when the output stops consuming temporarily.
        now = perf_counter()
        if self._audio_last_feed is not None:
            self._audio_max_feed_gap = max(self._audio_max_feed_gap,
                                           now - self._audio_last_feed)
        self._audio_last_feed = now
        self._pending_audio.extend(pcm)
        if len(self._pending_audio) > 38400:
            excess = (len(self._pending_audio) - 38400 + 3) // 4 * 4
            del self._pending_audio[:excess]
            self._audio_dropped_bytes += excess
        if not self._audio_timer.isActive():
            self._audio_timer.start()
        self._drain_audio()
        if self._sink is not None and now - self._audio_stats_at >= 5:
            pk_trace("audio.playback.stats", view=self.title.text(),
                     pending_ms=round(
                         len(self._pending_audio) * 1000 / self.AUDIO_BYTES_PER_SECOND,
                         2),
                     device_buffer_ms=round(
                         (self._sink.bufferSize() - self._sink.bytesFree())
                         * 1000 / self.AUDIO_BYTES_PER_SECOND, 2),
                     max_feed_gap_ms=round(self._audio_max_feed_gap * 1000, 2),
                     underruns=self._audio_underruns,
                     dropped_bytes=self._audio_dropped_bytes)
            self._audio_stats_at, self._audio_max_feed_gap = now, 0.0

    def _drain_audio(self):
        if self._sink is None or not self._pending_audio:
            self._audio_timer.stop()
            return
        if self._audio_buffering:
            # Starting with a single 20 ms packet leaves no allowance for
            # receive/UI scheduling jitter. Also refill after a real underrun,
            # rather than repeatedly restarting playback with an empty queue.
            if len(self._pending_audio) < self.AUDIO_PREFILL_BYTES:
                self._audio_timer.stop()
                return
            self._audio_buffering = False
        try:
            sink, device = self._sink, self._device
            available = min(len(self._pending_audio), sink.bytesFree())
            if device and available > 0 and self._sink is sink:
                written = device.write(bytes(self._pending_audio[:available]))
                if self._sink is not sink:  # write() may synchronously report an output error.
                    return
                if written < 0:
                    self._audio_failed(
                        "已收到声音，但本机音频输出写入失败；将自动重试")
                else:
                    del self._pending_audio[:written]
                    if sink.error() == QtAudio.Error.NoError:
                        self._audio_status("")
            if not self._pending_audio:
                self._audio_timer.stop()
        except (RuntimeError, OSError):
            self._audio_failed("已收到声音，但本机音频播放失败；将自动重试")

    def _audio_status(self, message):
        if message != self.audio_status.text():
            pk_trace("audio.playback.status", view=self.title.text(),
                     message=message)
        self.audio_status.setText(message)
        self.audio_status.setVisible(bool(message))

    def _audio_failed(self, message):
        pk_trace("audio.playback.failed", view=self.title.text(),
                 message=message)
        self._release_audio()
        self._audio_retry_at = monotonic() + 2
        if not self._muted:
            self._audio_status(message)

    def _audio_state_changed(self, sink):
        if sink is None or sink is not self._sink:
            return
        state = sink.state()
        error = sink.error()
        if (error in (QtAudio.Error.OpenError, QtAudio.Error.IOError,
                      QtAudio.Error.FatalError)
                or state == QtAudio.State.StoppedState):
            self._audio_failed("已收到声音，但本机音频播放已中断；将自动重试")
        elif state == QtAudio.State.IdleState or error == QtAudio.Error.UnderrunError:
            # A temporarily empty audio queue can recover with the next packet;
            # do not recreate the device on every ordinary playback underrun.
            self._audio_buffering = True
            if self._audio_running:
                self._audio_running = False
                self._audio_underruns += 1
                pk_trace("audio.playback.underrun", view=self.title.text(),
                         pending_bytes=len(self._pending_audio),
                         count=self._audio_underruns)
                self._audio_status("本机播放暂时缺少音频数据，正在等待声音")
        elif state == QtAudio.State.ActiveState:
            self._audio_running = True
            self._audio_status("")

    def _release_audio(self):
        self._audio_timer.stop()
        self._pending_audio.clear()
        self._audio_buffering = True
        self._audio_running = False
        self._audio_last_feed = None
        self._audio_max_feed_gap = 0.0
        self._audio_stats_at = perf_counter()
        self._audio_underruns = self._audio_dropped_bytes = 0
        sink, self._sink = self._sink, None
        self._device = None
        if sink is not None:
            sink.stop()
            sink.deleteLater()
            pk_trace("audio.playback.closed", view=self.title.text())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._render()

    def reset(self):
        self._preview_generation += 1
        self._preview_packet = None
        self._image_is_cropped = False
        self._release_audio()
        self._audio_retry_at = 0.0
        self._audio_status("")
        self._image = None
        self._render()
        self.imageChanged.emit(None)
        self.video.clear()
        self.video.setText("等待画面")
