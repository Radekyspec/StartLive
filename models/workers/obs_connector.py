# package import
from PySide6.QtCore import Slot
from obsws_python import ReqClient

# local package import
import config
from models.log import get_logger
from models.workers.base import BaseWorker, run_wrapper
from .obs_daemon import ObsDaemonWorker


class ObsConnectorWorker(BaseWorker):
    def __init__(self, host, port, password):
        super().__init__(name="OBS通讯")
        self.host = host
        self.port = port
        self.password = password
        self.logger = get_logger(self.__class__.__name__)

    @Slot()
    @run_wrapper
    def run(self, /) -> None:
        config.obs_op = True
        config.obs_connecting = True
        self.logger.info("OBS connecting")
        config.obs_client = ReqClient(host=self.host, port=self.port,
                                      password=self.password,
                                      timeout=5)
        config.obs_op = False
        config.obs_connecting = False

    @classmethod
    def on_exception(cls, parent_window: "StreamConfigPanel", *args, **kwargs):
        logger = get_logger(cls.__name__)
        logger.error(f"OBS connect failed.")
        parent_window.obs_auto_live_checkbox.setEnabled(False)
        config.obs_op = False
        config.obs_connecting = False

    @classmethod
    def on_finished(cls, parent_window):
        logger = get_logger(cls.__name__)
        if config.obs_client is not None:
            logger.info("OBS connected")
            parent_window.obs_auto_live_checkbox.setEnabled(True)
            parent_window.parent_window.add_thread(
                ObsDaemonWorker(),
                on_finished=ObsDaemonWorker.on_finished
            )
