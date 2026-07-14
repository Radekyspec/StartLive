from src.core import app_state
from src.core.workers.base import Presenter


class FetchQRPresenter(Presenter):
    def __init__(self, view: "MainWindow"):
        super().__init__()
        self._view = view

    def prepare_success_view(self):
        self._view.update_qr_image(app_state.scan_status["qr_url"])

    def prepare_fail_view(self, exception: Exception): ...

    def prepare_progress_view(self, *args, **kwargs): ...
