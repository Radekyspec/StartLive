from threading import Condition
from typing import Callable

from startlive.core import app_state
from startlive.core.workers.base import BaseWorker, Presenter


class WaitObsConnectedWorker(BaseWorker):
    def __init__(self, presenter: Presenter, cond: Condition):
        super().__init__(name="wait_obs_connected",
                         with_session=False, presenter=presenter)
        self._cond = cond

    def run(self, report_progress: Callable | None, *args, **kwargs):
        with self._cond:
            while app_state.obs_connecting:
                self._cond.wait()
