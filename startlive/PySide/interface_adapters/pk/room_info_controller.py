from time import monotonic

from startlive.core.exceptions import PkError
from startlive.core.pk.identity import require_current_identity
from startlive.core.pk.trace import pk_trace
from startlive.core.workers.pk.fetch_room_info import PkRoomInfoWorker
from .pk_presenter import PkPresenter


class PkRoomInfoController:
    """Normal anchor's first post-Pub HTTP query and current RTC room updates.

    All methods run on the owner's dispatcher. New connection flows opt into
    the captured two-second cadence; existing video PK keeps explicit refresh.
    """

    def __init__(self, manager, identity, session, *, changed, polling_stopped,
                 failed,
                 identity_guard=require_current_identity, poll_interval=None,
                 clock=monotonic, snapshot_guard=None):
        self.manager, self.identity, self.session = manager, identity, session
        self.changed, self.polling_stopped, self.failed = changed, polling_stopped, failed
        self.identity_guard = identity_guard
        self.busy = self._published = self._closed = False
        self.poll_interval, self.clock = poll_interval, clock
        self.snapshot_guard = snapshot_guard
        self.next_poll = 0.0

    def tick(self):
        if (self.poll_interval is not None and self._published
                and not self._closed and self.clock() >= self.next_poll):
            self.refresh()

    def published(self):
        """Call only after the RTC Pub RPC/description update completed."""
        if self._closed or self._published:
            return False
        self._published = True
        return self.refresh()

    def refresh(self):
        if self._closed or self.busy or self.session.stop_polling:
            return False
        if not self._published:
            raise PkError("请等待本机音视频发布完成后再查询连线房间")
        self.identity_guard(self.identity)
        self.busy = True
        self.next_poll = self.clock() + (self.poll_interval or 0)
        request = {"biz_session_id": self.session.biz_session_id,
                   "room_id": str(self.identity.room_id)}
        try:
            controls_current = self.snapshot_guard() if self.snapshot_guard else None
            worker = PkRoomInfoWorker(PkPresenter(
                finished=lambda result: self._loaded(result, request=request,
                                                     controls_current=controls_current),
                failed=self._failed),
                self.identity, self.session.biz_session_id)
            worker.request_allowed = lambda: not self._closed and not self.session.stop_polling
            self.manager.submit(worker)
        except Exception as error:
            self._trace_failure(error, request=request, response=None,
                                stage="submit")
            self._failed(error)
        return True

    def _loaded(self, result, *, request, controls_current=None):
        self.busy = False
        if self._closed:
            return
        try:
            self.identity_guard(self.identity)
            was_stopped = self.session.stop_polling
            batch = self.session.accept_http(result.data)
            for info in batch.infos:
                if controls_current is None:
                    self.changed(info)
                else:
                    self.changed(info, apply_controls=controls_current())
            if batch.stop_polling and not was_stopped:
                self.polling_stopped()
        except Exception as error:
            self._trace_failure(error, request=request, response=result,
                                stage="callback")
            self._failed(error)

    def receive_rtc(self, message):
        if self._closed:
            return
        try:
            self.identity_guard(self.identity)
            info = self.session.receive_rtc(message)
            if info is not None:
                self.changed(info)
        except Exception as error:
            self._trace_failure(error, response=message,
                                stage="rtc_notification")
            self.failed(error)

    def _trace_failure(self, error, **fields):
        pk_trace("room.info.failed", uid=self.identity.uid,
                 room_id=self.identity.room_id,
                 operation="universal_info", error_type=type(error).__name__,
                 error=str(error), **fields)

    def _failed(self, error):
        self.busy = False
        if not self._closed:
            self.failed(error)

    def close(self):
        self._closed = True
        self.session.close()
