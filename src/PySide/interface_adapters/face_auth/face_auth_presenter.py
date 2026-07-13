from contextlib import suppress

from src.core.workers.base import Presenter


class FaceAuthPresenter(Presenter):
    def __init__(self, view: "FaceQRWidget"):
        super().__init__()
        self._view = view

    def prepare_success_view(self):
        with suppress(RuntimeError):
            self._view.deleteLater()

    def prepare_fail_view(self, *args, **kwargs): ...

    def prepare_progress_view(self, *args, **kwargs): ...
