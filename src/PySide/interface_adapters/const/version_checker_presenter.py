from src.PySide.states import LoginState
from src.core.workers.base import Presenter


class VersionCheckerPresenter(Presenter):
    def __init__(self, state: LoginState):
        super().__init__()
        self._state = state

    def prepare_success_view(self, version: str | None = None):
        if version is not None:
            self._state.versionChecked.emit(version)

    def prepare_fail_view(self, exception: Exception): ...

    def prepare_progress_view(self, *args, **kwargs): ...
