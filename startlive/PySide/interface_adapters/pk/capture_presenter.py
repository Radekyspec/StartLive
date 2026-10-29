"""OBS capture lifecycle callbacks, including manager-dispatched cancellation."""
from startlive.core.workers.base import Presenter


class PkCapturePresenter(Presenter):
    def __init__(self, window, worker):
        self.window, self.worker = window, worker

    def prepare_success_view(self):
        self.window._preview_stopped(self.worker)

    def prepare_cancel_view(self):
        self.prepare_success_view()

    def prepare_fail_view(self, exception):
        self.window._preview_failed(exception.real_exc, self.worker)

    def prepare_progress_view(self, _):
        self.window._preview_connected(self.worker)
