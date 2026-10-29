"""Release round-query ownership on every terminal worker result."""
from startlive.core.workers.base import Presenter


class PkRoundQueryPresenter(Presenter):
    def __init__(self, owner, serial, pk_id, *, classic):
        self.owner, self.serial, self.pk_id = owner, serial, pk_id
        self.classic = classic

    def prepare_success_view(self, result):
        self.owner._queried(self.serial, self.pk_id, result, classic=self.classic)

    def prepare_fail_view(self, exception):
        self.owner._query_failed(self.serial, exception.real_exc,
                                 pk_id=self.pk_id, classic=self.classic)

    def prepare_cancel_view(self):
        self.owner._take_reply(self.serial)

    def prepare_progress_view(self, *args, **kwargs):
        pass
