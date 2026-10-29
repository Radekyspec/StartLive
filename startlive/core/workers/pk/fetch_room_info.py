from startlive.core.exceptions import PkProtocolError
from .pk_request import PkRequestWorker


class PkRoomInfoWorker(PkRequestWorker):
    """Contract22 normal anchor bootstrap after successful publication."""
    operation = "universal_info"

    def __init__(self, presenter, identity, /, biz_session_id: str):
        super().__init__(presenter, identity,
                         fields={"biz_session_id": biz_session_id,
                                 "room_id": str(identity.room_id)})

    def parse_result(self, data):
        if not isinstance(data, dict):
            raise PkProtocolError("连线房间查询缺少 data 对象")
        return data
