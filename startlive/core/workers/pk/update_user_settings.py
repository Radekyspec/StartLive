from startlive.core.exceptions import PkProtocolError
from startlive.core.pk.identity import require_current_identity
from startlive.core.pk.states.user_settings import PkUserSettingsSaved, \
    PkUserSettingsSnapshot
from .pk_request import PkRequestWorker


class UpdatePkUserSettingsWorker(PkRequestWorker):
    operation = "update_user_settings"

    def __init__(self, presenter, identity, /, snapshot):
        if not isinstance(snapshot, PkUserSettingsSnapshot):
            raise PkProtocolError("请先读取当前账号的完整 PK 设置")
        self.snapshot = snapshot
        super().__init__(presenter, identity, fields=snapshot.business_fields())

    def parse_result(self, result):
        require_current_identity(self.identity)
        message = result.data.get("msg") if isinstance(result.data,
                                                       dict) else None
        return PkUserSettingsSaved(self.snapshot,
                                   message if isinstance(message, str) else "")
