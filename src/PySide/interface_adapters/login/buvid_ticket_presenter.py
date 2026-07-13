from src.core.workers.base import Presenter
from src.core.workers.credentials.credential_manager import \
    CredentialManagerWorker


class BuvidTicketPresenter(Presenter):
    def prepare_success_view(self):
        CredentialManagerWorker.add_cookie(True)

    def prepare_fail_view(self): ...

    def prepare_progress_view(self, *args, **kwargs): ...
