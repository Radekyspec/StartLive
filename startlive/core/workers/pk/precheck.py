from startlive.core.pk.parameters import precheck_fields
from startlive.core.pk.precheck import parse_precheck
from .pk_request import PkRequestWorker


class _PkPrecheckWorker(PkRequestWorker):
    operation = "precheck"

    def __init__(self, presenter, identity, /, kind, *, trace_id):
        super().__init__(presenter, identity,
                         fields=precheck_fields(identity, kind),
                         after_sign={"client_traceid": trace_id})

    def parse_result(self, result):
        return parse_precheck(result.data)


class PkMatchPrecheckWorker(_PkPrecheckWorker):
    """Preflight for random/classic matchmaking."""


class PkInvitePrecheckWorker(_PkPrecheckWorker):
    """Preflight for a selected outgoing invitation."""
