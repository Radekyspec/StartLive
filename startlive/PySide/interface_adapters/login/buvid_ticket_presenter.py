from startlive.core import app_state
from startlive.core.credentials import CredentialStore
from startlive.core.workers.base import Presenter


class TicketFetchPresenter(Presenter):
    def prepare_success_view(self, account_generation: int):
        with app_state.account_lock:
            if not app_state.account_is_current(account_generation):
                return
            CredentialStore().add(
                dict(app_state.cookies_dict), allow_duplicate=True
            )

    def prepare_fail_view(self, exception: Exception): ...

    def prepare_progress_view(self, *args, **kwargs): ...
