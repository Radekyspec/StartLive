from startlive.core.exceptions import PkError, PkProtocolError
from startlive.core.pk.events import invitation_context_from_event
from startlive.core.pk.trace import pk_trace
from startlive.core.workers.pk.handle_invitation import (
    PkAcceptInvitationWorker, PkRejectInvitationWorker,
    PkAcceptRoomInvitationWorker, PkRejectRoomInvitationWorker,
)
from .request_attempt import RequestAttempt


class PkHandleController:
    """Handle a preserved invitation snapshot after an explicit eligibility decision."""

    def __init__(self, manager, identity, join_controller, *, handled, failed):
        self.manager, self.identity, self.join_controller = manager, identity, join_controller
        self.handled, self.failed = handled, failed
        self.busy = False
        self._attempt = RequestAttempt()

    def retire(self):
        """Discard callbacks from the previous interaction without cancelling HTTP."""
        self._attempt.invalidate()
        self.busy = False

    def handle_event(self, event, *, accept, eligibility=None, app_room=None,
                     room_id=0):
        context = invitation_context_from_event(event)
        if context.source not in (5, 7, 10, 11, 12):
            raise PkError("当前邀请来源尚未接入")
        if context.source == 12:
            if app_room is None:
                raise PkError("此邀请需要先确认当前房间上下文")
            if event.target_room_id is not None and event.target_room_id > 0 and event.target_room_id != self.identity.room_id:
                raise PkError("此邀请不属于当前直播间")
        self.handle(context, accept=accept, eligibility=eligibility,
                    app_room=bool(app_room), room_id=room_id)

    def handle(self, context, *, accept, eligibility=None, app_room=False,
               room_id=0):
        if self.busy:
            raise PkError("邀请操作正在处理")
        if accept and (eligibility is None or eligibility.allowed is not True):
            raise PkError((
                              eligibility.reason if eligibility else "") or "当前尚不能确认是否可接受此邀请")
        if type(accept) is not bool:
            raise PkProtocolError("邀请操作必须明确为接受或拒绝")
        worker_type = ((
                           PkAcceptRoomInvitationWorker if accept else PkRejectRoomInvitationWorker)
                       if app_room else (
            PkAcceptInvitationWorker if accept else PkRejectInvitationWorker))
        self._attempt.invalidate()
        worker = worker_type(
            self._attempt.presenter(
                lambda result: self._handled(result, operation=worker.operation,
                                             request=worker.fields | worker.after_sign),
                self._failed), self.identity, context,
            room_id=room_id)
        self.busy = True
        try:
            self.manager.submit(worker)
        except Exception as error:
            self._trace_failure(error, operation=worker.operation,
                                request=worker.fields | worker.after_sign,
                                response=None, stage="submit")
            worker.on_exception(error)

    def _handled(self, result, *, operation, request):
        self.busy = False
        try:
            if result.join_event is not None:
                # Native JoinChannelByApiResponse precedes Handle listener notification.
                self.join_controller.handle(result.join_event)
        except Exception as error:
            self._trace_failure(error, operation=operation, request=request,
                                response=result.response, stage="callback")
            self.failed(error)
            return
        self.handled(result.response)

    def _trace_failure(self, error, **fields):
        pk_trace("invitation.handle.failed", uid=self.identity.uid,
                 room_id=self.identity.room_id,
                 error_type=type(error).__name__, error=str(error), **fields)

    def _failed(self, error):
        self.busy = False
        self.failed(error)
