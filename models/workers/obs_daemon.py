# module import
from contextlib import suppress
from queue import Empty

# package import
from PySide6.QtCore import Slot

# local package import
import config
from models.log import get_logger
from models.workers.base import LongLiveWorker, run_wrapper


# package import


class ObsDaemonWorker(LongLiveWorker):
    def __init__(self):
        super().__init__(name="OBS交互")

    @Slot()
    @run_wrapper
    def run(self, /):
        while config.obs_client is not None and self.is_running:
            with suppress(Empty):
                req, body = config.obs_req_queue.get(timeout=.2)
                config.obs_client.send(req, body)

    @classmethod
    def disconnect_obs(cls):
        logger = get_logger(cls.__name__)
        logger.info("OBS disconnecting")
        config.obs_op = True
        if config.obs_client is not None:
            config.obs_client.disconnect()
        logger.info("OBS disconnected")
        config.obs_client = None
        config.obs_op = False

    @classmethod
    @Slot()
    def on_finished(cls):
        if config.obs_client is not None:
            cls.disconnect_obs()
