"""Translate manager-dispatched RTC results into the owning GUI lifecycle."""
from startlive.core.workers.base import Presenter


class PkRtcPresenter(Presenter):
    def __init__(self, owner, worker, generation):
        self.owner, self.worker, self.generation = owner, worker, generation

    def prepare_success_view(self):
        self.owner.finished(self.worker)

    def prepare_cancel_view(self):
        self.prepare_success_view()

    def prepare_fail_view(self, exception):
        self.owner.finished(self.worker, exception.real_exc)

    def prepare_progress_view(self, value):
        owner = self.owner
        if (self.worker is owner.worker and self.generation == owner.generation
                and owner.future is not None and not owner.future.done()):
            owner.progress(value)
