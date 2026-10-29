from startlive.core.exceptions import PkProtocolError
from startlive.core.pk.events import join_from_handle_response
from startlive.core.pk.parameters import handle_invitation_fields
from .pk_request import PkRequestWorker


class PkHandleInvitationWorker(PkRequestWorker):
    operation = "handle"

    def __init__(self, presenter, identity, /, event, *, accept, app_room=False, room_id=0,
                 include_trace=True):
        self.operation = "handle_room" if app_room else "handle"
        if self.operation == "handle_room":
            if event.handle_source != 12 or room_id <= 0:
                raise PkProtocolError(
                    "房间邀请处理缺少已确认的场景和房间上下文")
        super().__init__(presenter, identity,
                         fields=handle_invitation_fields(event,
                                                         accept=accept,
                                                         room_id=room_id),
                         after_sign={
                             "client_traceid": event.trace_id or ""} if include_trace else {})

    def parse_result(self, result):
        return result, join_from_handle_response(result)
