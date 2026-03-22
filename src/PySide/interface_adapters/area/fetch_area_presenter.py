from src.core.workers.base import Presenter
from ...states import LoginState


class FetchAreaPresenter(Presenter):
    def __init__(self, state: LoginState):
        super().__init__()
        self.state = state

    def prepare_success_view(self):
        self.state.areaUpdated.emit()

    def prepare_fail_view(self):
        self.state.areaUpdated.emit()

    def prepare_progress_view(self): ...
