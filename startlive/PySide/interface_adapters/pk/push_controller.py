"""PK selects its business decoder; danmaku owns the connection workers."""
from startlive.core.danmaku.connection import DanmakuConnection
from startlive.core.workers.danmaku.acknowledge import DanmakuAckWorker
from startlive.core.workers.pk.push import PkPushWorker


class PkPushController(DanmakuConnection):
    def __init__(self, manager, identity, *, ready, event, failed,
                 state_changed=None,
                 settings=None, push_factory=PkPushWorker,
                 ack_factory=DanmakuAckWorker):
        super().__init__(manager, identity, ready=ready, event=event,
                         failed=failed,
                         state_changed=state_changed, settings=settings,
                         push_factory=push_factory, ack_factory=ack_factory)
