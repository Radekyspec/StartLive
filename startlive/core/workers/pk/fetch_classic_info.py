from startlive.core.exceptions import PkProtocolError
from .pk_request import PkRequestWorker


class PkClassicInfoWorker(PkRequestWorker):
    """Contract16 secret62ed0 variant, without pk_version or post-sign CSRF."""
    operation = "classic_info"

    def __init__(self, presenter, identity, /, pk_id, *, current_state=False):
        # Contract44 permits zero only for an explicit owner current-state
        # refresh; ordinary round lookup still requires a positive ID.
        if (type(pk_id) is not int or pk_id < 0 or (
                pk_id == 0 and not current_state)
                or (current_state and pk_id != 0)):
            raise PkProtocolError("传统 PK 查询缺少有效的回合 ID")
        super().__init__(presenter, identity,
                         fields={"is_anchor": "1", "pk_id": str(pk_id),
                                 "room_id": str(identity.room_id)})
