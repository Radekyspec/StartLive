"""Deliver manager-owned searches to the current account's open dialog."""
from startlive.core.pk.identity import require_current_identity
from startlive.core.workers.base import Presenter


class PkSearchPresenter(Presenter):
    def __init__(self, dialog):
        self.dialog = dialog

    def prepare_success_view(self, page):
        if self.dialog._closed:
            return
        try:
            require_current_identity(self.dialog.identity)
            self.dialog._loaded(page)
        except Exception as error:
            self.dialog._failed(error)

    def prepare_fail_view(self, exception):
        self.dialog._failed(exception.real_exc)

    def prepare_cancel_view(self):
        if not self.dialog._closed:
            self.dialog._busy = False
            self.dialog.status.setText("查找已取消，可重新查找。")
            self.dialog._update_controls()

    def prepare_progress_view(self, *args, **kwargs):
        pass
