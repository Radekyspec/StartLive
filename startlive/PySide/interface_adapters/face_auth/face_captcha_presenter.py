from startlive.PySide.states import StreamState
from startlive.core import app_state
from startlive.core.constant import FaceAuthType
from startlive.core.workers.base import Presenter


class FaceCaptchaPresenter(Presenter):
    def __init__(self, view: "MainWindow", state: StreamState):
        super().__init__()
        self._view = view
        self._state = state

    def prepare_success_view(self):
        self._state.faceRequired.emit(
            app_state.stream_status["face_url"], FaceAuthType.V2)

    def prepare_fail_view(self, exception: Exception): ...

    def prepare_progress_view(self, *args, **kwargs): ...
