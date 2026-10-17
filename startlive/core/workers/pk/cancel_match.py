from .pk_request import PkRequestWorker
from startlive.core.pk.parameters import cancel_match_fields


class PkCancelMatchWorker(PkRequestWorker):
    operation = "cancel_match"

    def __init__(self, presenter, identity, /, kind, *, trace_id,
                 need_warn=False, group_battle=False):
        super().__init__(presenter, identity,
                         fields=cancel_match_fields(identity, kind,
                                                    need_warn=need_warn,
                                                    group_battle=group_battle),
                         after_sign={
                             "client_traceid": trace_id} if trace_id else {})
