from threading import Condition

from startlive.PySide.log import get_logger
from startlive.PySide.states import ObsBtnState
from startlive.core import app_state
from startlive.core.workers.base import Presenter
from startlive.core.workers.obs_ws import ObsDaemonWorker


class ObsConnectorPresenter(Presenter):
    def __init__(self, view: "StreamConfigPanel", state: ObsBtnState,
                 cond: Condition):
        super().__init__()
        self._view = view
        self._state = state
        self._cond = cond
        self.logger = get_logger(self.__class__.__name__)

    def prepare_success_view(self):
        if app_state.obs_client is not None:
            self._state.obsConnected.emit()
            self.logger.info("OBS connected")
            self._view.obs_auto_live_checkbox.setEnabled(True)
            from startlive.PySide.interface_adapters.obs_ws import \
                ObsDaemonPresenter

            self._view.parent_window.add_thread(
                ObsDaemonWorker(ObsDaemonPresenter()))

    def prepare_fail_view(self, exception: Exception):
        self.logger.error(f"OBS connect failed.")
        self._view.obs_auto_live_checkbox.setEnabled(False)
        with self._cond:
            app_state.obs_op = False
            app_state.obs_connecting = False
            self._cond.notify_all()
        self._state.obsDisconnected.emit()

    def prepare_progress_view(self):
        self._state.obsConnecting.emit()
