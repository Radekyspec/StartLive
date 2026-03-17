from src.core.workers.base import Presenter
from ...states import LoginState


class FetchAreaPresenter(Presenter):
    def __init__(self, state: LoginState):
        self.state = state

    def prepare_success_view(self):
        self.state.areaUpdated.emit()

    def prepare_fail_view(self):
        self.state.areaUpdated.emit()
