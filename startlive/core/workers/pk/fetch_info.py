from startlive.core.pk.pk_info import queried_pk_info
from .pk_request import PkRequestWorker


class PkInfoWorker(PkRequestWorker):
    """Contract27: signed GET, own room and round ID, post-sign CSRF."""
    operation = "info"

    def __init__(self, presenter, identity, /, pk_id: int):
        super().__init__(presenter, identity, fields={"pk_id": f"{pk_id:d}",
                                                      "room_id": str(
                                                          identity.room_id)})

    def parse_result(self, data):
        return queried_pk_info(data)
