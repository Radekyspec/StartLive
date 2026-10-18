# module import
from contextlib import suppress
from queue import Empty
from time import monotonic
from typing import Callable

from obsws_python.error import OBSSDKRequestError

from startlive.core import app_state
from startlive.core.obs.states.output import ObsOutputStatus
from startlive.core.log import get_logger
from startlive.core.workers.base import LongLiveWorker, Presenter


# package import


class ObsDaemonWorker(LongLiveWorker):
    def __init__(self, presenter: Presenter, /):
        super().__init__(name="OBS交互", with_session=False,
                         presenter=presenter)

    def run(self, report_progress: Callable | None, *args, **kwargs):
        next_status = 0
        try:
            while app_state.obs_client is not None and self.is_running:
                # All OBS requests stay on this daemon: ReqClient's socket must
                # not be read concurrently by a second PK worker.
                client = app_state.obs_client
                if monotonic() >= next_status:
                    try:
                        result = client.send("GetStreamStatus", raw=True)
                        active, reconnecting = result.get(
                            "outputActive"), result.get("outputReconnecting")
                        if type(active) is not bool or type(
                                reconnecting) is not bool:
                            raise ValueError("Invalid OBS output observation")
                        app_state.obs_output_status = ObsOutputStatus(active,
                                                                      reconnecting,
                                                                      monotonic())
                    except Exception:
                        app_state.obs_output_status = ObsOutputStatus()
                    next_status = monotonic() + 1
                try:
                    item = app_state.obs_req_queue.get(timeout=.2)
                except Empty:
                    continue
                req, body = item
                with suppress(OBSSDKRequestError):
                    client.send(req, body)
        finally:
            app_state.obs_output_status = ObsOutputStatus()

    @classmethod
    def disconnect_obs(cls):
        logger = get_logger(cls.__name__)
        logger.info("OBS disconnecting")
        app_state.obs_op = True
        app_state.obs_output_status = ObsOutputStatus()
        if app_state.obs_client is not None:
            app_state.obs_client.disconnect()
            app_state.obs_client = None
        logger.info("OBS disconnected")
        app_state.obs_op = False
