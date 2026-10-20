from startlive.core.pk.parameters import mute_fields
from .pk_request import PkRequestWorker


class PkMuteWorker(PkRequestWorker):
    operation = "mute"

    def __init__(self, presenter, identity, /, biz_session_id, target_uid, *,
                 media, remote, muted):
        super().__init__(presenter, identity, fields=mute_fields(
            biz_session_id, target_uid, media=media, remote=remote,
            muted=muted, room_id=identity.room_id if not remote else 0))
