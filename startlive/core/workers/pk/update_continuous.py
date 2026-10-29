from startlive.core.pk.parameters import continuous_fields, parse_continuous_status
from .pk_request import PkRequestWorker


class UpdateContinuousPkWorker(PkRequestWorker):
    """Write the switch, then return the server-confirmed status."""
    operation = "continuous_update"

    def __init__(self, presenter, identity, /, kind, enabled, *, trace_id):
        super().__init__(presenter, identity,
                         fields=continuous_fields(identity, kind, enabled,
                                                  trace_id))

    def run(self, report_progress, *args, **kwargs):
        super().run(report_progress)
        return self._request(
            "continuous_status", {},
            parse_result=parse_continuous_status)
