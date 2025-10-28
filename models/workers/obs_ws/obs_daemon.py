# module import
from contextlib import suppress
from queue import Empty

# package import
from PySide6.QtCore import Slot

# local package import
import app_state
from models.log import get_logger
from models.states import ObsBtnState
from models.workers.base import LongLiveWorker, run_wrapper


# package import


class ObsDaemonWorker(LongLiveWorker):
    def __init__(self):
        super().__init__(name="OBS交互", with_session=False)

    @Slot()
    @run_wrapper
    def run(self, /):
        while app_state.obs_client is not None and self.is_running:
            with suppress(Empty):
                req, body = app_state.obs_req_queue.get(timeout=.2)
                app_state.obs_client.send(req, body)

    @classmethod
    def disconnect_obs(cls, state: ObsBtnState):
        logger = get_logger(cls.__name__)
        logger.info("OBS disconnecting")
        app_state.obs_op = True
        if app_state.obs_client is not None:
            app_state.obs_client.disconnect()
        logger.info("OBS disconnected")
        state.obsDisconnected.emit()
        app_state.obs_client = None
        app_state.obs_op = False

    @Slot()
    def on_finished(self, state: ObsBtnState):
        if app_state.obs_client is not None:
            self.disconnect_obs(state)
