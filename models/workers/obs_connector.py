from functools import partial

# package import
from PySide6.QtCore import Slot, QMutex, QWaitCondition, QMutexLocker
from obsws_python import ReqClient

# local package import
import config
from models.log import get_logger
from models.states import ObsBtnState
from models.workers.base import BaseWorker, run_wrapper
from .obs_daemon import ObsDaemonWorker


class ObsConnectorWorker(BaseWorker):
    def __init__(self, state: ObsBtnState, /, mutex: QMutex,
                 cond: QWaitCondition, *, host, port, password):
        super().__init__(name="OBS通讯")
        self._mutex = mutex
        self._cond = cond
        self.host = host
        self.port = port
        self.password = password
        self.state = state
        self.logger = get_logger(self.__class__.__name__)

    @Slot()
    @run_wrapper
    def run(self, /) -> None:
        with QMutexLocker(self._mutex):
            config.obs_op = True
            config.obs_connecting = True
            self._cond.wakeAll()
        self.state.obsConnecting.emit()
        self.logger.info("OBS connecting")
        config.obs_client = ReqClient(host=self.host, port=self.port,
                                      password=self.password,
                                      timeout=5)
        with QMutexLocker(self._mutex):
            config.obs_op = False
            config.obs_connecting = False
            self._cond.wakeAll()

    @Slot()
    def on_exception(self, parent_window: "StreamConfigPanel",
                     state: ObsBtnState,
                     *args, **kwargs):
        self.logger.error(f"OBS connect failed.")
        parent_window.obs_auto_live_checkbox.setEnabled(False)
        with QMutexLocker(self._mutex):
            config.obs_op = False
            config.obs_connecting = False
            self._cond.wakeAll()
        state.obsDisconnected.emit()

    @Slot()
    def on_finished(self, parent_window, state: ObsBtnState):
        self._session.close()
        if config.obs_client is not None:
            state.obsConnected.emit()
            self.logger.info("OBS connected")
            parent_window.obs_auto_live_checkbox.setEnabled(True)
            obs_daemon = ObsDaemonWorker()
            parent_window.parent_window.add_thread(
                obs_daemon,
                on_finished=partial(obs_daemon.on_finished, state)
            )
