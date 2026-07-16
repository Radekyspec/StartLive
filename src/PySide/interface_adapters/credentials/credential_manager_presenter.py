from src.PySide.interface_adapters.login import FetchLoginPresenter
from src.core import app_state
from src.core.workers.base import Presenter
from src.core.workers.usernames import FetchUsernamesWorker


class CredentialManagerPresenter(Presenter):
    def __init__(self, view: "MainWindow", state) -> None:
        super().__init__()
        self._view = view
        self._state = state

    def prepare_success_view(self, cookie_index: int):
        FetchLoginPresenter.post_login(self._view, self._state)
        if not app_state.scan_status["is_new"]:
            fetch_usernames = FetchUsernamesWorker(
                app_state.cookie_indices[cookie_index]
            )
            self._view.add_thread(
                fetch_usernames
            )
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

    def prepare_fail_view(self, exception: Exception):
        self._state.credentialLoaded.emit()

    def prepare_progress_view(self, *args, **kwargs): ...
