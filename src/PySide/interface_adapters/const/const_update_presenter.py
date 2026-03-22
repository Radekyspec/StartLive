from src.PySide.states import LoginState
from src.core import app_state
from src.core.workers.base import Presenter


class ConstantUpdatePresenter(Presenter):
    def __init__(self, state: LoginState):
        super().__init__()
        self._state = state

    def prepare_success_view(self):
        app_state.scan_status["const_updated"] = True
        self._state.constUpdated.emit()

    def prepare_fail_view(self):
        app_state.scan_status["const_updated"] = True
        self._state.constUpdated.emit()

    def prepare_progress_view(self, progress: int):
        pass
