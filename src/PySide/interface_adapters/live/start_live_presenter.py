from threading import Condition

from PySide6.QtWidgets import QMessageBox

from src.PySide.states import StreamState
from src.core import app_state
from src.core.workers.base import Presenter


class StartLivePresenter(Presenter):
    def __init__(self, view: "StreamConfigPanel", state: StreamState, /,
                 cond: Condition) -> None:
        super().__init__()
        self._view = view
        self._state = state
        self._cond = cond

    def prepare_success_view(self, live_result):
        match live_result:
            case 0:
                with self._cond:
                    while app_state.obs_connecting:
                        self._cond.wait()
                self._state.addressUpdated.emit(
                    app_state.stream_status["stream_addr"],
                    app_state.stream_status["stream_key"])
            case 1:
                QMessageBox.warning(self._view, "无可用SRT流",
                                    "没有检测到可用的SRT服务器，已切换到RTMP协议")
                with self._cond:
                    while app_state.obs_connecting:
                        self._cond.wait()
                self._state.addressUpdated.emit(
                    app_state.stream_status["stream_addr"],
                    app_state.stream_status["stream_key"])
            case -1:
                QMessageBox.warning(self._view, "无可用SRT流",
                                    "没有检测到可用的SRT服务器，已停止直播")
                self._view.stop_btn.click()
            case 60024:
                self._state.faceRequired.emit(
                    app_state.stream_status["face_url"])

    def prepare_fail_view(self, exception: Exception):
        self._view.start_btn.setEnabled(True)
        self._view.parent_window.tray_start_live_action.setEnabled(True)
        self._view.stop_btn.setEnabled(False)
        self._view.parent_window.tray_stop_live_action.setEnabled(False)
        self._view.modify_area_btn.setEnabled(True)

    def prepare_progress_view(self, *args, **kwargs):
        ...
