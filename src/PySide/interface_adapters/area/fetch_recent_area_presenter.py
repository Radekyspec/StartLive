from src.core import app_state
from src.core.workers.base import Presenter


class FetchRecentAreaPresenter(Presenter):
    def __init__(self, view):
        self._view = view

    def prepare_success_view(self):
        self._view.historyUpdated.emit(app_state.room_info["recent_areas"])

    def prepare_fail_view(self):
        self._view.historyUpdated.emit([])
