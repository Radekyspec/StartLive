from startlive.core.exceptions import PkProtocolError
from .pk_request import PkRequestWorker


class PkRoomInfoWorker(PkRequestWorker):
    """Contract22 normal anchor bootstrap after successful publication."""
    operation = "universal_info"

    def __init__(self, presenter, identity, /, biz_session_id):
        if not isinstance(biz_session_id, str) or not biz_session_id:
            raise PkProtocolError("连线房间查询缺少业务会话")
        super().__init__(presenter, identity,
                         fields={"biz_session_id": biz_session_id,
                                 "room_id": str(identity.room_id)})
