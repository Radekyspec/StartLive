from threading import Condition
from typing import TYPE_CHECKING

from src.core import app_state
from src.core.workers.base import Presenter
from src.core.workers.obs_ws import ObsDaemonWorker
from src.PySide.log import get_logger
from src.PySide.states import ObsBtnState

if TYPE_CHECKING:
    from src.PySide.window.stream_config import StreamConfigPanel


class ObsConnectorPresenter(Presenter):
    def __init__(self, view: "StreamConfigPanel", state: ObsBtnState,
                 cond: Condition) -> None:
        super().__init__()
        self._view = view
        self._state = state
        self._cond = cond
        self.logger = get_logger(self.__class__.__name__)

    def prepare_success_view(self) -> None:
        if app_state.obs_client is not None:
            self._state.obsConnected.emit()
            self.logger.info("OBS connected")
            self._view.obs_auto_live_checkbox.setEnabled(True)
            from src.PySide.interface_adapters.obs_ws import ObsDaemonPresenter

            self._view.parent_window.add_thread(
                ObsDaemonWorker(ObsDaemonPresenter()))

    def prepare_fail_view(self, exception: Exception) -> None:
        self.logger.error("OBS connect failed.")
        self._view.obs_auto_live_checkbox.setEnabled(False)
        with self._cond:
            app_state.obs_op = False
            app_state.obs_connecting = False
            self._cond.notify_all()
        self._state.obsDisconnected.emit()

    def prepare_progress_view(self) -> None:
        self._state.obsConnecting.emit()
