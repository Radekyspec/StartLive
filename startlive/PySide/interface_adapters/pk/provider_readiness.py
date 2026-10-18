"""One import check per window, with replaceable owner continuations.

All methods and callbacks run on the existing GUI dispatcher. Readiness caches
imports only: each caller must recheck account, output and invitation state.
"""
from startlive.core.pk.trace import pk_trace
from startlive.core.workers.base.CallbackPresenter import CallbackPresenter
from startlive.core.workers.pk.provider_preflight import \
    PkProviderPreflightWorker


class VideoProviderReadiness:
    def __init__(self, manager, check=None):
        self.manager, self.check = manager, check
        self.ready = False
        self._worker = None
        self._waiters = {}
        self._closed = False

    def waiting(self, owner):
        return owner in self._waiters

    def ensure(self, owner, ready, failed):
        if self._closed:
            return
        if self.ready:
            self._waiters.pop(owner, None)
            self._deliver(ready, failed)
            return
        self._waiters[owner] = (ready, failed)
        if self._worker is not None:
            return
        worker = PkProviderPreflightWorker(CallbackPresenter(
            finished=lambda: self._completed(worker),
            failed=lambda error: self._completed(worker, error)), self.check)
        self._worker = worker
        try:
            self.manager.submit(worker)
        except Exception as error:
            worker.on_exception(error)

    def cancel(self, owner):
        # Keep the in-flight import check available for a replacement owner.
        self._waiters.pop(owner, None)

    def close(self):
        self._closed = True
        self._waiters.clear()
        if self._worker is not None:
            self._worker.stop()
            self._worker = None

    def _completed(self, worker, error=None):
        if self._closed or worker is not self._worker:
            return
        self._worker = None
        self.ready = error is None
        # A callback may cancel/replace another owner. Consult the live map
        # before delivering, and leave new waiters to their new check.
        for owner, callbacks in tuple(self._waiters.items()):
            if self._waiters.get(owner) is callbacks:
                del self._waiters[owner]
                try:
                    self._deliver(*callbacks, error=error)
                except Exception as callback_error:
                    # One observer must not strand other owners after the check
                    # has completed and there is no worker left to wake them.
                    pk_trace("provider.callback.failed",
                             error_type=type(callback_error).__name__)

    @staticmethod
    def _deliver(ready, failed, *, error=None):
        if error is not None:
            failed(error)
            return
        try:
            ready()
        except Exception as error:
            failed(error)
