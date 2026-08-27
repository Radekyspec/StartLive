from typing import TYPE_CHECKING

from src.PySide.interface_adapters.title import RecentTitlePresenter
from src.PySide.states import LoginState
from src.core import app_state
from src.core.constant import CoverStatus
from src.core.workers.base import Presenter
from src.core.workers.title import LoadRecentTitleWorker

if TYPE_CHECKING:
    from src.PySide.window.stream_config import StreamConfigPanel


class FetchPreLivePresenter(Presenter):
    def __init__(self, view: "StreamConfigPanel", state: LoginState):
        super().__init__()
        self._view = view
        self._state = state

    def prepare_success_view(self):
        title_text = app_state.room_info["title"]
        app_state.room_info["recent_title"].insert(0, title_text)
        self._view.title_input.currentTextChanged.connect(
            lambda: self._view.save_title_btn.setEnabled(True))
        self._view.parent_window.add_thread(
            LoadRecentTitleWorker(RecentTitlePresenter(self._view)))
        if app_state.stream_status["live_status"]:
            self._view.addr_input.setText(
                app_state.stream_status["stream_addr"])
            self._view.key_input.setText(
                app_state.stream_status["stream_key"])
            self._view.start_btn.setEnabled(False)
            self._view.parent_window.tray_start_live_action.setEnabled(False)
            self._view.stop_btn.setEnabled(True)
            self._view.parent_window.tray_stop_live_action.setEnabled(True)
        self._view.cover_audit_state()
        if app_state.room_info["cover_status"] == CoverStatus.AUDIT_IN_PROGRESS:
            self._view.ensure_cover_audit_monitor()
        self._state.roomUpdated.emit()

    def prepare_fail_view(self, exception: Exception):
        ...

    def prepare_progress_view(self, *args, **kwargs):
        ...
