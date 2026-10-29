from startlive.core.exceptions import TaskCancelled
from startlive.core.pk.api import PkApi
from startlive.core.pk.identity import require_current_identity
from startlive.core.pk.states.session import PkIdentity
from startlive.core.workers.base import BaseWorker, Presenter


class PkRequestWorker(BaseWorker):
    """Manager-owned HTTP work; results are data or parsed domain values."""
    operation: str

    def __init__(self, presenter: Presenter, identity: PkIdentity, /,
                 fields: dict[str, str], *, after_sign=None):
        super().__init__(name="PK 请求", presenter=presenter,
                         defer_session=True,
                         account_cookies=dict(identity.cookies))
        self.identity = identity
        self.fields = fields.copy()
        self.after_sign = {} if after_sign is None else after_sign.copy()
        self.request_allowed = None

    def _before_send(self):
        if self.request_allowed is not None and not self.request_allowed():
            raise TaskCancelled()
        require_current_identity(self.identity)

    def run(self, report_progress, *args, **kwargs):
        return self._request(self.operation, self.fields,
                             after_sign=self.after_sign,
                             parse_result=self.parse_result)

    def _request(self, operation, fields, *, after_sign=None, parse_result=None):
        """Each step shares this worker's HTTP session and admission guard."""
        return PkApi(self._session, self.identity,
                     logger_name=type(self).__name__).request(
            operation, fields, after_sign=after_sign,
            parse_result=parse_result, before_send=self._before_send)

    def parse_result(self, result):
        """Parse while the transport still owns this request's log context."""
        return result
