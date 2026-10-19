from startlive.core.pk.parameters import continuous_fields
from .pk_request import PkRequestWorker


class UpdateContinuousPkWorker(PkRequestWorker):
    operation = "continuous_update"

    def __init__(self, presenter, identity, /, kind, enabled, *, trace_id):
        super().__init__(presenter, identity,
                         fields=continuous_fields(identity, kind, enabled,
                                                  trace_id))
