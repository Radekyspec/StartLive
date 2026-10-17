from .pk_request import PkRequestWorker
from startlive.core.pk.parameters import match_fields


class PkMatchWorker(PkRequestWorker):
    operation = "match"

    def __init__(self, presenter, identity, /, kind, *, trace_id,
                 theme_id=None):
        extra = {"client_traceid": trace_id}
        if theme_id is not None:
            extra["theme_id"] = str(theme_id)
        super().__init__(presenter, identity,
                         fields=match_fields(identity, kind), after_sign=extra)
