from contextlib import suppress

from src.core.workers.base import Presenter


class FaceAuthPresenter(Presenter):
    def __init__(self, view: "FaceQRWidget"):
        super().__init__()
        self._view = view

    def prepare_success_view(self, result: int):
        if result == 1:
            with suppress(RuntimeError):
                self._view.deleteLater()
        if result == 2:
            self._view.face_hint.setText("二维码已失效")

    def prepare_fail_view(self, exception: Exception): ...

    def prepare_progress_view(self, *args, **kwargs): ...
