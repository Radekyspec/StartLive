from startlive.core.exceptions import DanmakuError
from .settings import settings_for_identity
from startlive.core.constant.danmaku import DanmakuState
from startlive.core.workers.base.CallbackPresenter import CallbackPresenter
from startlive.core.workers.danmaku.acknowledge import DanmakuAckWorker
from startlive.core.workers.danmaku.connection import DanmakuWorker


class DanmakuConnection:
    """Own both push workers; callbacks are dispatched by the session manager.

    Initial authentication invokes ready once. Reauthentication reports state
    without starting a second match/invitation. Either worker failing stops
    both, so a broken HTTP ACK queue cannot leave an apparently healthy socket.
    """

    def __init__(self, manager, identity, *, ready, event, failed,
                 state_changed=None,
                 settings=None, push_factory=DanmakuWorker,
                 ack_factory=DanmakuAckWorker):
        self.manager, self.identity = manager, identity
        self.ready, self.event, self.failed, self.state_changed = ready, event, failed, state_changed
        self.settings = settings or settings_for_identity(identity)
        self.push_factory, self.ack_factory = push_factory, ack_factory
        self.running = self.authenticated = False
        self._generation = 0
        self._ready_called = False
        self._workers, self._futures = [], []

    def start(self):
        if self.running:
            return
        if any(not future.done() for future in self._futures):
            raise DanmakuError("弹幕服务仍在关闭，请稍后重试")
        self._generation += 1
        generation = self._generation
        self.running, self.authenticated, self._ready_called = True, False, False
        self._workers, self._futures = [], []

        def failure(error):
            if self.running and generation == self._generation:
                self.stop()
                self.failed(error)

        def unexpected_finish():
            failure(DanmakuError("弹幕服务意外停止"))

        def progress(value):
            if not self.running or generation != self._generation:
                return
            if isinstance(value, DanmakuState):
                self.authenticated = value is DanmakuState.AUTHENTICATED
                if self.state_changed:
                    self.state_changed(value)
                if self.authenticated and not self._ready_called:
                    self._ready_called = True
                    self.ready()
            elif self.authenticated:
                self.event(value)

        try:
            ack = self.ack_factory(
                CallbackPresenter(finished=unexpected_finish, failed=failure),
                self.identity)
            self._workers.append(ack)
            push = self.push_factory(
                CallbackPresenter(finished=unexpected_finish, failed=failure,
                                  progress=progress),
                self.identity, settings=self.settings, sequence_ack=ack.enqueue)
            self._workers.append(push)
            for worker in self._workers:
                self._futures.append(
                    self.manager.submit(worker, on_progress=True))
        except Exception as error:
            # Deferred sessions are only opened/closed inside started workers.
            for worker in self._workers[len(self._futures):]:
                worker.stop()
            failure(error)

    def stop(self):
        self.running = self.authenticated = False
        self._generation += 1
        for worker in self._workers:
            worker.stop()
        for future in self._futures:
            future.cancel()
