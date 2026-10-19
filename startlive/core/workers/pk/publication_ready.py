"""Native business2 notification after successful RTC Pub (main3e18fc)."""
from startlive.core.pk.events import join_from_handle_response
from startlive.core.pk.states.events import PkHandleResult
from .pk_request import PkRequestWorker


class PkPublicationReadyWorker(PkRequestWorker):
    operation = "handle"

    def __init__(self, presenter, identity, /):
        # The native post-Pub caller passes empty session/trace, not the JOIN
        # session or invitation trace. The constructor omits empty trace_id.
        super().__init__(presenter, identity, fields={
            "peer_uid": "0", "action": "4", "action_type": "0",
            "source": "0", "biz_session_id": "",
        })

    def parse_result(self, result):
        return PkHandleResult(result,
                              join_from_handle_response(result.data))
