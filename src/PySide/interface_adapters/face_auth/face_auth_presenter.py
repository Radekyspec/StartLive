from contextlib import suppress

from src.core.workers.base import Presenter


class FaceAuthPresenter(Presenter):
    def prepare_success_view(self, qr_window):
        with suppress(RuntimeError):
            qr_window.deleteLater()

    def prepare_fail_view(self, *args, **kwargs): ...

    def prepare_progress_view(self, *args, **kwargs): ...
