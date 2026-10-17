"""Thread-safe change notifications for PK snapshots.

This intentionally has no Qt dependency. Subscribers run on the thread that
updates the state; a GUI subscriber must forward the notification to a queued
Qt signal instead of touching widgets from that thread.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
import logging

from .app_state_base import StateBase


@dataclass(slots=True)
class ObservableState(StateBase):
    _subscribers: set[Callable[[], None]] = field(
        init=False, repr=False, compare=False, default_factory=set)

    def subscribe(self, callback: Callable[[], None]) -> None:
        with self._lock:
            self._subscribers.add(callback)

    def unsubscribe(self, callback: Callable[[], None]) -> None:
        with self._lock:
            self._subscribers.discard(callback)

    def _on_change(self) -> None:
        self._notify()

    def _notify(self) -> None:
        with self._lock:
            listeners = tuple(self._subscribers)
        for listener in listeners:
            try:
                listener()
            except Exception:
                # OBS/RTC state updates must not fail due to a closing widget.
                logging.getLogger(__name__).exception(
                    "PK state subscriber failed")
