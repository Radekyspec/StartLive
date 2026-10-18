from startlive.core.pk.identity import require_current_identity
from startlive.core.pk.user_settings import parse_user_settings
from .pk_request import PkRequestWorker


class FetchPkUserSettingsWorker(PkRequestWorker):
    operation = "user_settings"

    def __init__(self, presenter, identity, /):
        super().__init__(presenter, identity, fields={})

    def parse_result(self, result):
        require_current_identity(self.identity)
        return parse_user_settings(result.data)
