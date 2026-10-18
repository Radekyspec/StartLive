from startlive.core import app_state
from startlive.core.workers.base import Presenter
from startlive.core.workers.obs_ws import ObsDaemonWorker


class ObsDaemonPresenter(Presenter):
    def prepare_success_view(self):
        if app_state.obs_client is not None:
            ObsDaemonWorker.disconnect_obs()

    def prepare_fail_view(self, exception: Exception): ...

    def prepare_progress_view(self, *args, **kwargs): ...
