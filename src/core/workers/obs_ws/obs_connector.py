from threading import Condition
from typing import Callable

from obsws_python import ReqClient

# local package import
from src.core import app_state
# package import
from src.core.log import get_logger
from src.core.workers.base import BaseWorker, Presenter


class ObsConnectorWorker(BaseWorker):
    def __init__(self, presenter: Presenter, /,
                 host, port, password, *, cond: Condition):
        super().__init__(name="OBS通讯", with_session=False,
                         presenter=presenter)
        self.host = host
        self.port = port
        self.password = password
        self._cond = cond
        self.logger = get_logger(self.__class__.__name__)

    def run(self, report_progress: Callable | None, *args, **kwargs):
        with self._cond:
            app_state.obs_op = True
            app_state.obs_connecting = True
            self._cond.notify_all()
        report_progress()
        self.logger.info("OBS connecting")
        app_state.obs_client = ReqClient(host=self.host, port=self.port,
                                         password=self.password,
                                         timeout=5)
        with self._cond:
            app_state.obs_op = False
            app_state.obs_connecting = False
            self._cond.notify_all()
