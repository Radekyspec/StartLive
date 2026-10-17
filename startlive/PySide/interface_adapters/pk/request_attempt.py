"""Dispatcher-owned request generation, independent of worker admission keys."""
from .pk_presenter import PkPresenter


class RequestAttempt:
    def __init__(self):
        self.serial = 0
        self.inflight = False
        self.cancel_requested = False

    def invalidate(self):
        self.serial += 1

    def presenter(self, finished, failed, *, stale=None):
        serial = self.serial

        def deliver(callback, value):
            if serial == self.serial:
                callback(value)
            elif stale is not None:
                stale(serial)

        return PkPresenter(finished=lambda value: deliver(finished, value),
                           failed=lambda error: deliver(failed, error))

    @staticmethod
    def submit(manager, worker):
        try:
            manager.submit(worker)
        except Exception as error:
            worker.on_exception(error)
