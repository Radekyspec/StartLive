from startlive.PySide.states import StreamState
from startlive.core import app_state
from startlive.core.workers.base import Presenter


class WaitObsConnectedPresenter(Presenter):
    def __init__(self, state: StreamState):
        self._state = state

    def prepare_success_view(self):
        self._state.addressUpdated.emit(
            app_state.stream_status["stream_addr"],
            app_state.stream_status["stream_key"])

    def prepare_fail_view(self, exception: Exception): ...

    def prepare_progress_view(self, *args, **kwargs): ...
