from .pk_request import PkRequestWorker


class PkQuitConnectionWorker(PkRequestWorker):
    operation = "quit"

    def __init__(self, presenter, identity, /, biz_session_id, *, trace_id):
        super().__init__(presenter, identity,
                         fields={"biz_session_id": biz_session_id},
                         after_sign={"client_traceid": trace_id})
