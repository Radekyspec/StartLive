from threading import Event, Lock
from typing import Callable

from src.core.exceptions import TaskCancelled


class CancellationToken:
    def __init__(self) -> None:
        self._event = Event()
        self._callbacks: list[Callable[[], None]] = []
        self._lock = Lock()

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
                pass

    def is_cancelled(self) -> bool:
        return self._event.is_set()

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
