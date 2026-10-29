from time import monotonic

from startlive.core.exceptions import PkError
from startlive.core.pk.identity import require_current_identity
from startlive.core.pk.room_info import PkRoomInfoSession
from startlive.core.pk.trace import pk_trace
from startlive.core.workers.pk.fetch_room_info import PkRoomInfoWorker
from startlive.core.workers.base.CallbackPresenter import CallbackPresenter


class PkRoomInfoController:
    """Normal anchor's first post-Pub HTTP query and current RTC room updates.

    All methods run on the owner's dispatcher, with a two-second poll cadence.
    Each response is bound to this RTC owner and the mute revision at submission.
    """

    def __init__(self, rtc, join_event):
        self.rtc = rtc
        self.manager, self.identity = rtc.session.manager, rtc.session.identity
        self.session = PkRoomInfoSession(join_event)
        self.busy = self._published = self._closed = False
        self.next_poll = 0.0

    def tick(self):
        if (self._published and not self._closed
                and not self.session.stop_polling and monotonic() >= self.next_poll):
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
        require_current_identity(self.identity)
        self.busy = True
        self.next_poll = monotonic() + 2
        request = {"biz_session_id": self.session.biz_session_id,
                   "room_id": str(self.identity.room_id)}
        try:
            controls = self.rtc.business_mute
            revision = controls.snapshot_revision
            worker = PkRoomInfoWorker(CallbackPresenter(
                finished=lambda result: self._loaded(result, request=request,
                                                     controls=controls, revision=revision),
                failed=self._failed),
                self.identity, self.session.biz_session_id)
            worker.request_allowed = lambda: not self._closed and not self.session.stop_polling
            self.manager.submit(worker)
        except Exception as error:
            self._trace_failure(error, request=request, response=None,
                                stage="submit")
            self._failed(error)
        return True

    def _loaded(self, result, *, request, controls, revision):
        self.busy = False
        if self._closed:
            return
        try:
            require_current_identity(self.identity)
            for info in self.session.accept_http(result):
                self.rtc.room_changed(
                    info, apply_controls=controls is self.rtc.business_mute
                    and revision is not None and revision == controls.snapshot_revision)
        except Exception as error:
            self._trace_failure(error, request=request, response=result,
                                stage="callback")
            self._failed(error)

    def receive_rtc(self, message):
        if self._closed:
            return
        try:
            require_current_identity(self.identity)
            info = self.session.receive_rtc(message)
            if info is not None:
                self.rtc.room_changed(info)
        except Exception as error:
            self._trace_failure(error, response=message,
                                stage="rtc_notification")
            self.rtc.session._fatal(error)

    def _trace_failure(self, error, **fields):
        pk_trace("room.info.failed", uid=self.identity.uid,
                 room_id=self.identity.room_id,
                 operation="universal_info", error_type=type(error).__name__,
                 error=str(error), **fields)

    def _failed(self, error):
        self.busy = False
        if not self._closed:
            self.rtc.session._fatal(error)

    def close(self):
        self._closed = True
        self.session.close()
