from startlive.core.pk.states.session import PkIdentity
from startlive.core.pk.api import PkApi
from startlive.core.pk.identity import require_current_identity
from startlive.core.workers.base import BaseWorker, Presenter


class PkRequestWorker(BaseWorker):
    """Shared transport, with named operation subclasses in separate files."""
    operation: str

    def __init__(self, presenter: Presenter, identity: PkIdentity, /,
                 fields: dict[str, str], *, after_sign=None):
        super().__init__(name="PK 请求", presenter=presenter,
                         defer_session=True,
                         account_cookies=dict(identity.cookies))
        self.identity = identity
        self.fields = dict(fields)
        self.after_sign = dict(after_sign or {})

    def run(self, report_progress, *args, **kwargs):
        return PkApi(self._session, self.identity,
                     logger_name=type(self).__name__).request(
            self.operation, self.fields, after_sign=self.after_sign,
            parse_result=self.parse_result,
            before_send=lambda: require_current_identity(self.identity))

    def parse_result(self, result):
        """Parse while the transport still owns this request's log context."""
        return result
