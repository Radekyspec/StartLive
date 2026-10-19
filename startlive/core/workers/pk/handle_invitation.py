from startlive.core.exceptions import PkProtocolError
from startlive.core.pk.events import join_from_handle_response
from startlive.core.pk.parameters import handle_invitation_fields
from startlive.core.pk.states.events import PkHandleResult
from .pk_request import PkRequestWorker


class _PkHandleInvitationWorker(PkRequestWorker):
    operation = "handle"
    accept = False

    def __init__(self, presenter, identity, /, context, *, room_id=0,
                 include_trace=True):
        if self.operation == "handle_room":
            if context.source != 12 or room_id <= 0:
                raise PkProtocolError(
                    "房间邀请处理缺少已确认的场景和房间上下文")
        super().__init__(presenter, identity,
                         fields=handle_invitation_fields(context,
                                                         accept=self.accept,
                                                         room_id=room_id),
                         after_sign={
                             "client_traceid": context.trace_id} if include_trace else {})

    def parse_result(self, response):
        return PkHandleResult(response,
                              join_from_handle_response(response.data))


class PkAcceptInvitationWorker(_PkHandleInvitationWorker):
    accept = True


class PkRejectInvitationWorker(_PkHandleInvitationWorker):
    accept = False


class PkAcceptRoomInvitationWorker(PkAcceptInvitationWorker):
    operation = "handle_room"


class PkRejectRoomInvitationWorker(PkRejectInvitationWorker):
    operation = "handle_room"
