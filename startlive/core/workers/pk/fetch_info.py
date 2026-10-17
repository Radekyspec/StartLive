from .pk_request import PkRequestWorker
from startlive.core.exceptions import PkProtocolError


class PkInfoWorker(PkRequestWorker):
    """Contract27: signed GET, own room and round ID, post-sign CSRF."""
    operation = "info"

    def __init__(self, presenter, identity, /, pk_id):
        if type(pk_id) is not int or not 0 <= pk_id < 1 << 63:
            raise PkProtocolError("PK 查询缺少有效的回合 ID")
        super().__init__(presenter, identity, fields={"pk_id": str(pk_id),
                                                      "room_id": str(
                                                          identity.room_id)})
