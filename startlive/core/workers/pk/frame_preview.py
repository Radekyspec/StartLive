"""One bounded preview conversion loop for the PK window's two panes."""
from queue import Empty, Full, Queue

from startlive.core.exceptions import PkError
from startlive.core.workers.base import LongLiveWorker


class PkFramePreviewWorker(LongLiveWorker):
    def __init__(self, presenter):
        super().__init__(name="PK 画面预览", presenter=presenter, with_session=False)
        self._requests = Queue(maxsize=2)

    def request(self, channel, generation, packet, rectangle, pixels):
        self.raise_if_cancelled()
        try:
            self._requests.put_nowait((channel, generation, packet, rectangle, pixels))
        except Full as error:
            raise PkError("PK 预览转换请求积压，尚有画面未处理") from error

    def run(self, report_progress, *args, **kwargs):
        from av.video.reformatter import Interpolation, VideoReformatter
        from startlive.core.pk.video_frames import packet_frame, reformat_packet

        reformatters = [(VideoReformatter(), VideoReformatter()) for _ in range(2)]
        while self.is_running:
            try:
                channel, generation, packet, rectangle, pixels = self._requests.get(timeout=0.1)
            except Empty:
                continue
            self.raise_if_cancelled()

            def convert(frame, bounds, reformatter, interpolation):
                scale = min(1, bounds[0] / frame.width, bounds[1] / frame.height)
                return reformat_packet(
                    reformatter, frame, packet,
                    width=max(1, round(frame.width * scale)),
                    height=max(1, round(frame.height * scale)),
                    format="bgra", dst_color_range="JPEG", interpolation=interpolation)

            # Crop the source before scaling. The selector retains the full view.
            image = convert(packet_frame(packet, rectangle), pixels,
                            reformatters[channel][0], Interpolation.LANCZOS)
            thumbnail = (convert(packet_frame(packet), (960, 768),
                                 reformatters[channel][1], Interpolation.BILINEAR)
                         if rectangle is not None else image)
            self.raise_if_cancelled()
            report_progress(channel, generation, (image, thumbnail),
                            (packet.width, packet.height))
