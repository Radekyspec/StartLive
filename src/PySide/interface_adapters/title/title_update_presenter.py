from src.core import app_state
from src.core.workers.base import Presenter


class TitleUpdatePresenter(Presenter):
    def __init__(self, view: "StreamConfigPanel"):
        super().__init__()
        self._view = view

    def prepare_success_view(self):
        self._view.title_input.clear()
        self._view.title_input.addItems(app_state.room_info["recent_title"])

    def prepare_fail_view(self, exception: Exception):
        self._view.save_title_btn.setEnabled(True)

    def prepare_progress_view(self, *args, **kwargs): ...
