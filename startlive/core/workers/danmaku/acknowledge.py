"""Keep HTTP sequence acknowledgements off the socket/heartbeat thread."""
from queue import Empty, Full, Queue

from startlive.core.exceptions import DanmakuAuthenticationError, DanmakuError
from startlive.core.danmaku.api import DanmakuApi
from startlive.core.danmaku.identity import require_current_identity
from startlive.core.workers.base import LongLiveWorker


class DanmakuAckWorker(LongLiveWorker):
    def __init__(self, presenter, identity, /, *, api_factory=DanmakuApi,
                 identity_guard=require_current_identity):
        super().__init__(name="弹幕消息确认队列", presenter=presenter,
                         defer_session=True,
                         account_cookies=dict(identity.cookies))
        self.identity = identity
        self.api_factory, self.identity_guard = api_factory, identity_guard
        # Explicit StartLive backpressure policy, not a native cache limit.
        # Overflow fails the submitting push worker instead of losing ACKs.
        self._pending = Queue(maxsize=256)

    def enqueue(self, identity, queue_uuid, sequences):
        """Pass this directly as DanmakuWorker.sequence_ack.

        queue_uuid is context metadata; the confirmed HTTP form has no such
        field. Preserve separate batches across socket/context transitions.
        """
        self.raise_if_cancelled()
        if identity != self.identity:
            raise DanmakuAuthenticationError("消息确认账号与推送账号不一致")
        batch = tuple(sequences)
        if not batch:
            return
        try:
            self._pending.put_nowait(batch)
        except Full:
            raise DanmakuError("消息确认请求积压，请重新连接 弹幕服务") from None

    def run(self, report_progress, *args, **kwargs):
        try:
            api = self.api_factory(self._session, self.identity)
            while True:
                self.raise_if_cancelled()
                try:
                    batch = self._pending.get(timeout=0.25)
                except Empty:
                    continue
                self.raise_if_cancelled()
                self.identity_guard(self.identity)
                result = api.acknowledge_push_sequences(batch)
                self.raise_if_cancelled()
                if report_progress:
                    report_progress(result)
        finally:
            # A failed HTTP worker cannot silently keep accepting new batches.
            self.stop()
