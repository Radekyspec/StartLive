from src.core import app_state
from src.core.workers.base import Presenter


class RecentTitlePresenter(Presenter):
    def __init__(self, view: "StreamConfigPanel"):
        super().__init__()
        self._view = view

    def prepare_success_view(self, recent_title: list[str]):
        for title in recent_title:
            if title in app_state.room_info["recent_title"]:
                continue
            app_state.room_info["recent_title"].append(title)
        self._view.title_input.clear()
        self._view.title_input.addItems(app_state.room_info["recent_title"])

    def prepare_fail_view(self, exception: Exception):
        ...

    def prepare_progress_view(self, *args, **kwargs):
        ...
