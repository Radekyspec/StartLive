from startlive.core.exceptions import PkError, PkProtocolError
from startlive.core.pk.identity import require_current_identity
from startlive.core.pk.states.user_settings import PkUserSettingsSnapshot
from startlive.core.pk.user_settings import parse_user_settings
from .pk_request import PkRequestWorker


class UpdatePkUserSettingsWorker(PkRequestWorker):
    """Write, read back and verify on one manager-owned HTTP session."""
    operation = "update_user_settings"

    def __init__(self, presenter, identity, /, snapshot: PkUserSettingsSnapshot):
        self.snapshot = snapshot
        super().__init__(presenter, identity, fields=snapshot.business_fields())

    def run(self, report_progress, *args, **kwargs):
        result = super().run(report_progress)
        confirmed = self._request(
            "user_settings", {},
            parse_result=parse_user_settings)
        require_current_identity(self.identity)
        # Even a mismatch must display the current server snapshot. Manager
        # dispatches this progress before the final success/error callback.
        if report_progress is not None:
            report_progress(confirmed)
        if confirmed.preferences != self.snapshot.preferences:
            raise PkError("PK 设置回读与提交不一致，已显示服务端当前设置")
        return result

    def parse_result(self, data):
        # A successful write may omit data; malformed present fields are errors.
        if data is None:
            return ""
        message = data.get("msg", "")
        if not isinstance(message, str):
            raise PkProtocolError(
                f"PK 设置响应 msg 必须为文本，实际为 {type(message).__name__}")
        return message
