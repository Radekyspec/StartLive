from startlive.core.exceptions import PkError, PkProtocolError
from startlive.core.constant.pk import PkMode
from startlive.core.pk.trace import pk_trace
from startlive.core.workers.pk.handle_invitation import PkHandleInvitationWorker
from .request_attempt import RequestAttempt


class PkHandleController:
    """Handle a preserved invitation snapshot after an explicit eligibility decision."""

    def __init__(self, session):
        self.session = session
        self.manager, self.identity, self.rtc = session.manager, session.identity, session.rtc
        self.busy = False
        self._attempt = RequestAttempt()

    def retire(self):
        """Discard callbacks from the previous interaction without cancelling HTTP."""
        self._attempt.invalidate()
        self.busy = False

    def handle_event(self, event, *, accept, blocked_reason="尚未确认是否可接受此邀请", app_room=None,
                     room_id=0):
        source = event.handle_source
        if source not in (
                (4, 7) if self.session.options.mode == PkMode.VIDEO_LINK else (5, 7, 10, 11, 12)):
            raise PkError("当前邀请来源尚未接入")
        if source == 12:
            if app_room is None:
                raise PkError("此邀请需要先确认当前房间上下文")
            if event.target_room_id is not None and event.target_room_id > 0 and event.target_room_id != self.identity.room_id:
                raise PkError("此邀请不属于当前直播间")
        if self.busy:
            raise PkError("邀请操作正在处理")
        if accept and blocked_reason is not None:
            raise PkError(blocked_reason)
        if type(accept) is not bool:
            raise PkProtocolError("邀请操作必须明确为接受或拒绝")
        self._attempt.invalidate()
        worker = PkHandleInvitationWorker(
            self._attempt.presenter(
                lambda response, join_event: self._handled(response, join_event, operation=worker.operation,
                                             request=worker.fields | worker.after_sign),
                self._failed), self.identity, event,
            accept=accept, app_room=bool(app_room), room_id=room_id,
            include_trace=self.session.options.mode != PkMode.VIDEO_LINK)
        self.busy = True
        # Every mode gets the generation gate, not only video-link: stopLive
        # or a replacement invitation must stop a queued Handle from sending.
        serial = self._attempt.serial
        worker.request_allowed = lambda: serial == self._attempt.serial
        try:
            self.manager.submit(worker)
        except Exception as error:
            self._trace_failure(error, operation=worker.operation,
                                request=worker.fields | worker.after_sign,
                                response=None, stage="submit")
            worker.on_exception(error)

    def _handled(self, response, join_event, *, operation, request):
        self.busy = False
        try:
            if join_event is not None:
                # Native JoinChannelByApiResponse precedes Handle listener notification.
                self.rtc.handle_join(join_event)
        except Exception as error:
            self._trace_failure(error, operation=operation, request=request,
                                response=response, stage="callback")
            self.session.invitations.failed(error)
            return
        self.session.invitations.handled(response)

    def _trace_failure(self, error, **fields):
        pk_trace("invitation.handle.failed", uid=self.identity.uid,
                 room_id=self.identity.room_id,
                 error_type=type(error).__name__, error=str(error), **fields)

    def _failed(self, error):
        self.busy = False
        self.session.invitations.failed(error)
