from startlive.core.danmaku.api import DanmakuApi
from startlive.core.danmaku.identity import require_current_identity
from startlive.core.workers.base import BaseWorker


class AckDanmakuSequencesWorker(BaseWorker):
    def __init__(self, presenter, identity, /, sequences):
        super().__init__(name="弹幕消息序列确认", presenter=presenter,
                         defer_session=True,
                         account_cookies=dict(identity.cookies))
        self.identity, self.sequences = identity, tuple(sequences)

    def run(self, report_progress, *args, **kwargs):
        require_current_identity(self.identity)
        return DanmakuApi(self._session,
                          self.identity).acknowledge_push_sequences(
            self.sequences)
