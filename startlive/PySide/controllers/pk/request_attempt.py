"""Dispatcher-owned request generation, independent of worker admission keys."""
from startlive.core.workers.base.CallbackPresenter import CallbackPresenter


class RequestAttempt:
    def __init__(self):
        self.serial = 0
        self.inflight = False
        self.cancel_requested = False

    def invalidate(self):
        self.serial += 1

    def presenter(self, finished, failed, *, stale=None):
        serial = self.serial

        def deliver(callback, *args, **kwargs):
            if serial == self.serial:
                callback(*args, **kwargs)
            elif stale is not None:
                stale(serial)

        return CallbackPresenter(finished=lambda *args, **kwargs: deliver(finished, *args, **kwargs),
                           failed=lambda error: deliver(failed, error))

    def submit(self, manager, worker):
        # Bind the request to this attempt generation. A queued worker that
        # starts after retire/invalidate must not send: the room may already
        # be closed. Compose with any caller-supplied send gate.
        serial = self.serial
        previous = worker.request_allowed

        def allowed():
            return serial == self.serial and (
                previous is None or previous())

        worker.request_allowed = allowed
        try:
            manager.submit(worker)
        except Exception as error:
            worker.on_exception(error)
