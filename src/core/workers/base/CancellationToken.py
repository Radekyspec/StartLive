import logging
from collections.abc import Callable
from threading import Event, Lock

from ...exceptions import TaskCancelled

logger = logging.getLogger(__name__)


class CancellationToken:
    def __init__(self) -> None:
        self._event = Event()
        self._callbacks: list[Callable[[], None]] = []
        self._lock = Lock()

    def __bool__(self) -> bool:
        return self._event.is_set()

    def cancel(self) -> None:
        if self._event.is_set():
            return
        self._event.set()
        with self._lock:
            callbacks = list(self._callbacks)
        for cb in callbacks:
            try:
                cb()
            except Exception:
                # A callback must not prevent other cancellation callbacks.
                logger.debug("Cancellation callback failed", exc_info=True)
                continue

    def wait(self, timeout: float | None = None) -> bool:
        return self._event.wait(timeout)

    def raise_if_cancelled(self) -> None:
        if self._event.is_set():
            raise TaskCancelled()

    def add_cancel_callback(self, cb: Callable[[], None]) -> None:
        with self._lock:
            if self._event.is_set():
                run_now = True
            else:
                self._callbacks.append(cb)
                run_now = False
        if run_now:
            cb()
