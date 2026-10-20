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

    def submit(self, manager, worker):
        # Bind the request to this attempt generation. A queued worker that
        # starts after retire/invalidate must not send: the room may already
        # be closed. Compose with any caller-supplied send gate.
        serial = self.serial
        previous = getattr(worker, "request_allowed", None)

        def allowed():
            return serial == self.serial and (
                previous() if previous is not None else True)

        worker.request_allowed = allowed
        try:
            manager.submit(worker)
        except Exception as error:
            worker.on_exception(error)
