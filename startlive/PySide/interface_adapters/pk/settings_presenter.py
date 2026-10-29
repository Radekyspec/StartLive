"""Deliver settings snapshots only to the request's owning account and dialog."""
from startlive.core.workers.base import Presenter


class PkSettingsPresenter(Presenter):
    def __init__(self, owner, sequence, *, saving):
        self.owner, self.sequence, self.saving = owner, sequence, saving

    def _accept(self):
        if not self.owner._request_current(self.sequence):
            return False
        try:
            self.owner._require_account()
        except Exception as error:
            self.owner._failed(error)
            return False
        return True

    def prepare_success_view(self, result):
        if not self._accept():
            return
        try:
            if self.saving:
                self.owner._saved(result)
            else:
                self.owner._loaded(result)
        except Exception as error:
            self.owner._failed(error)

    def prepare_progress_view(self, snapshot):
        if not self._accept():
            return
        try:
            self.owner._show_snapshot(snapshot)
        except Exception as error:
            self.owner._failed(error)

    def prepare_fail_view(self, exception):
        if self._accept():
            self.owner._failed(exception.real_exc)

    def prepare_cancel_view(self):
        if self.owner._request_current(self.sequence):
            self.owner._finish_request()
