from src.core import app_state
from src.core.workers.base import Presenter


class FetchAnnouncePresenter(Presenter):
    def __init__(self, view) -> None:
        super().__init__()
        self._view = view

    def prepare_success_view(self):
        self._view.announce_input.setText(app_state.room_info["announcement"])
        self._view.announce_input.textEdited.connect(
            lambda: self._view.save_announce_btn.setEnabled(True))
