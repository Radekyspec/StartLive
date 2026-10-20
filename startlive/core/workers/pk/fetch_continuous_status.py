from startlive.core.pk.parameters import parse_continuous_status
from .pk_request import PkRequestWorker


class FetchContinuousPkStatusWorker(PkRequestWorker):
    operation = "continuous_status"

    def __init__(self, presenter, identity, /):
        super().__init__(presenter, identity, fields={})

    def parse_result(self, result):
        return parse_continuous_status(result.data)
