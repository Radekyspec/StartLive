# module import
from contextlib import suppress
from queue import Empty
from typing import Callable

# package import
from obsws_python.error import OBSSDKRequestError

# local package import
from src.core import app_state
from src.core.log import get_logger
from src.core.workers.base import LongLiveWorker, Presenter


# package import


class ObsDaemonWorker(LongLiveWorker):
    def __init__(self, presenter: Presenter, /):
        super().__init__(name="OBS交互", with_session=False,
                         presenter=presenter)

    def run(self, report_progress: Callable | None, *args, **kwargs):
        while app_state.obs_client is not None and self.is_running:
            with suppress(Empty):
                req, body = app_state.obs_req_queue.get(timeout=.2)
                with suppress(OBSSDKRequestError):
                    app_state.obs_client.send(req, body)

    @classmethod
    def disconnect_obs(cls):
        logger = get_logger(cls.__name__)
        logger.info("OBS disconnecting")
        app_state.obs_op = True
        if app_state.obs_client is not None:
            app_state.obs_client.disconnect()
            app_state.obs_client = None
        logger.info("OBS disconnected")
        app_state.obs_op = False
