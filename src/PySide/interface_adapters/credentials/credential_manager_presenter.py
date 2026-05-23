from src.core import app_state
from src.core.workers.base import Presenter
from src.core.workers.login import FetchLoginWorker
from src.core.workers.usernames import FetchUsernamesWorker


class CredentialManagerPresenter(Presenter):
    def __init__(self, parent_window, state, worker) -> None:
        super().__init__()
        self._view = parent_window
        self._state = state
        self._worker = worker

    def prepare_success_view(self):
        FetchLoginWorker.post_login(self._view, self._state)
        if not self._worker.is_new:
            fetch_usernames = FetchUsernamesWorker(
                app_state.cookie_indices[self._worker.cookie_index]
            )
            self._view.add_thread(
                fetch_usernames,
                on_finished=fetch_usernames.on_finished,
            )
        else:
            app_state.scan_status["is_new"] = True
        self._state.credentialLoaded.emit()
        panel = self._view.panel
        panel.host_input.setText(
            app_state.obs_settings.get("ip_addr", "localhost"))
        panel.port_input.setText(app_state.obs_settings.get("port", "4455"))
        panel.pass_input.setText(app_state.obs_settings.get("password", ""))
        panel.obs_auto_live_checkbox.setChecked(
            app_state.obs_settings.get("auto_live", False))
        panel.obs_auto_connect_checkbox.setChecked(
            app_state.obs_settings.get("auto_connect", False))

    def prepare_fail_view(self, *args, **kwargs):
        ...

    def prepare_progress_view(self, *args, **kwargs):
        ...
