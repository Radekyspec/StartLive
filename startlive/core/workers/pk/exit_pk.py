from startlive.core.pk.parameters import exit_pk_fields
from .pk_request import PkRequestWorker


class PkExitWorker(PkRequestWorker):
    operation = "exit"

    def __init__(self, presenter, identity, /, *, end_round):
        super().__init__(presenter, identity,
                         fields=exit_pk_fields(end_round=end_round))
