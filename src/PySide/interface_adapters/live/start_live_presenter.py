from threading import Condition

from PySide6.QtWidgets import QMessageBox

from src.PySide.interface_adapters.face_auth import FaceCaptchaPresenter
from src.PySide.interface_adapters.obs_ws import WaitObsConnectedPresenter
from src.PySide.states import StreamState
from src.core import app_state
from src.core.constant import FaceAuthType
from src.core.workers.base import Presenter
from src.core.workers.face_auth import FaceCaptchaWorker
from src.core.workers.live import ReportLiveDataWorker
from src.core.workers.obs_ws import WaitObsConnectedWorker


class StartLivePresenter(Presenter):
    def __init__(self, view: "StreamConfigPanel", state: StreamState, /,
                 cond: Condition) -> None:
        super().__init__()
        self._view = view
        self._state = state
        self._cond = cond

    def prepare_success_view(self, live_result):
        self._view.parent_window.add_thread(ReportLiveDataWorker())
        match live_result:
            case 0:
                self._view.parent_window.add_thread(
                    WaitObsConnectedWorker(
                        WaitObsConnectedPresenter(self._state), self._cond)
                )
            case 1:
                QMessageBox.warning(self._view, "无可用SRT流",
                                    "没有检测到可用的SRT服务器，已切换到RTMP协议")
                self._view.parent_window.add_thread(
                    WaitObsConnectedWorker(
                        WaitObsConnectedPresenter(self._state), self._cond)
                )
            case -1:
                QMessageBox.warning(self._view, "无可用SRT流",
                                    "没有检测到可用的SRT服务器，已停止直播")
                self._view.stop_btn.click()
            case FaceAuthType.V1:
                self._state.faceRequired.emit(
                    app_state.stream_status["face_url"], FaceAuthType.V1)
            case FaceAuthType.V2:
                self._view.parent_window.add_thread(
                    FaceCaptchaWorker(
                        FaceCaptchaPresenter(self._view.parent_window,
                                             self._state))
                )

    def prepare_fail_view(self, exception: Exception):
        self._view.start_btn.setEnabled(True)
        self._view.parent_window.tray_start_live_action.setEnabled(True)
        self._view.stop_btn.setEnabled(False)
        self._view.parent_window.tray_stop_live_action.setEnabled(False)
        self._view.modify_area_btn.setEnabled(True)

    def prepare_progress_view(self, *args, **kwargs):
        ...
