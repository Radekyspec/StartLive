"""PK event adapter; room connection lifetime belongs to core.danmaku."""
from startlive.core.pk.push_protocol import PkPushProtocol
from startlive.core.workers.danmaku.connection import DanmakuWorker


class PkPushWorker(DanmakuWorker):
    protocol_factory = PkPushProtocol
