from startlive.core.danmaku.api import DanmakuApi
from startlive.core.danmaku.identity import require_current_identity
from startlive.core.workers.base import BaseWorker


class FetchDanmakuBootstrapWorker(BaseWorker):
    def __init__(self, presenter, identity, /):
        super().__init__(name="获取弹幕连接信息", presenter=presenter,
                         defer_session=True,
                         account_cookies=dict(identity.cookies))
        self.identity = identity

    def run(self, report_progress, *args, **kwargs):
        require_current_identity(self.identity)
        return DanmakuApi(self._session, self.identity).fetch_push_bootstrap()
