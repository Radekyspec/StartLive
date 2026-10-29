"""Build Qt images on the GUI dispatcher from worker-owned BGRA frames."""
from PySide6.QtGui import QImage

from startlive.core.workers.base import Presenter


class PkFramePreviewPresenter(Presenter):
    def __init__(self, window, worker):
        self.window, self.worker = window, worker

    def prepare_progress_view(self, channel, generation, frames, source_size):
        window = self.window
        if window._shutdown or self.worker is not window._frame_preview_worker:
            return
        view = (window.local_view, window.remote_view)[channel]
        if generation != view._preview_generation:
            view._apply_preview(None, generation)
            return
        try:
            images = tuple(QImage(memoryview(frame.planes[0]), frame.width,
                                  frame.height, frame.planes[0].line_size,
                                  QImage.Format.Format_ARGB32).copy()
                           for frame in frames)
            images[1].setText("source_width", str(source_size[0]))
            images[1].setText("source_height", str(source_size[1]))
            view._apply_preview(images, generation)
        except Exception as error:
            view._preview_conversion_failed(error)

    def prepare_success_view(self):
        self.window._frame_preview_finished(self.worker)

    def prepare_cancel_view(self):
        self.prepare_success_view()

    def prepare_fail_view(self, exception):
        self.window._frame_preview_finished(self.worker, exception.real_exc)
