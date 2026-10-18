"""Isolated codec probing owned and cancelled by the existing worker manager."""
from threading import Event

from startlive.core.pk.video_encoder_backend import scan_encoders
from startlive.core.workers.base import LongLiveWorker


class ScanPkEncodersWorker(LongLiveWorker):
    def __init__(self, presenter):
        super().__init__(name="PK encoder detection", presenter=presenter,
                         with_session=False)
        self._cancel_event = Event()
        self.add_cancel_callback(self._cancel_event.set)

    def cancel_scan(self):
        # User cancellation returns a result to the open editor. Worker stop
        # instead belongs to owner shutdown, whose callbacks may be discarded.
        self._cancel_event.set()

    def run(self, report_progress, *args, **kwargs):
        self.raise_if_cancelled()
        # Wrap the tuple so WorkerManager forwards the catalogue as one value.
        return (scan_encoders(progress=report_progress,
                              cancel_event=self._cancel_event),)
