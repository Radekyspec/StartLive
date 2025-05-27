# module import
from contextlib import suppress
from queue import Empty

from PySide6.QtCore import Slot
# package import
from obsws_python import ReqClient

# local package import
import config
from .base import LongLiveWorker


class ObsDaemonWorker(LongLiveWorker):
    def __init__(self, parent_window: "StreamConfigPanel",
                 host, port, password):
        super().__init__(name="OBS通讯")
        self.parent_window = parent_window
        self.host = host
        self.port = port
        self.password = password

    @Slot()
    def run(self, /) -> None:
        config.obs_op = True
        try:
            config.obs_client = ReqClient(host=self.host, port=self.port,
                                          password=self.password,
                                          timeout=3)
            config.obs_op = False

        except Exception as e:
            self.exception = e
            config.obs_op = False
            self.parent_window.obs_auto_start_checkbox.setEnabled(False)
        else:
            self.parent_window.obs_auto_start_checkbox.setEnabled(True)
            while config.obs_client is not None and self._is_running:
                with suppress(Empty):
                    req, body = config.obs_req_queue.get(timeout=.2)
                    config.obs_client.send(req, body)
        finally:
            self.disconnect_obs()
            self.finished = True

    @staticmethod
    def disconnect_obs():
        config.obs_op = True
        if config.obs_client is not None:
            config.obs_client.disconnect()
        config.obs_client = None
        config.obs_op = False
