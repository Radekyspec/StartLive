from startlive.core.danmaku.api import DanmakuApi
from startlive.core.danmaku.client import DanmakuClient
from startlive.core.danmaku.protocol import DanmakuProtocol
from startlive.core.workers.base import LongLiveWorker


class DanmakuWorker(LongLiveWorker):
    protocol_factory = DanmakuProtocol

    def __init__(self, presenter, identity, /, *, settings, sequence_ack,
                 bootstrap=None, **options):
        super().__init__(name="弹幕连接", presenter=presenter,
                         defer_session=True,
                         with_session=bootstrap is None,
                         account_cookies=dict(identity.cookies))
        self.identity = identity
        self.client = DanmakuClient(identity, settings=settings,
                                    sequence_ack=sequence_ack,
                                    bootstrap=bootstrap or self._fetch_bootstrap,
                                    cancellation=self._cancel_token,
                                    protocol_factory=self.protocol_factory,
                                    **options)

    def _fetch_bootstrap(self, identity):
        return DanmakuApi(self._session, identity).fetch_push_bootstrap()

    def run(self, report_progress, *args, **kwargs):
        return self.client.run(report_progress)
