from startlive.core.constant.pk import NativePkType
from startlive.core.exceptions import PkError
from startlive.core.workers.pk.fetch_continuous_status import \
    FetchContinuousPkStatusWorker
from startlive.core.workers.pk.update_continuous import UpdateContinuousPkWorker
from startlive.core.workers.base.CallbackPresenter import CallbackPresenter


class PkContinuousController:
    """Video-random continuous PK reader; classic never owns one."""

    def __init__(self, session):
        self.session = session
        self.manager, self.identity = session.manager, session.identity
        self.kind = NativePkType.DOUBLE_RANDOM
        self.trace_id = session.trace_id
        self.status = None
        self.busy = False
        self.closed = False

    def close(self):
        """Retire this reader; a later read must not leave the closed owner."""
        self.closed = True
        self.busy = False

    def load(self, *, check_requeue=False):
        if self.closed:
            raise PkError("连续 PK 状态读取已关闭")
        if self.busy:
            raise PkError("正在读取或更新连续 PK 状态")
        self.busy = True
        self._submit(FetchContinuousPkStatusWorker(
            CallbackPresenter(
                finished=lambda status: self._loaded(status, check_requeue=check_requeue),
                failed=self._failed), self.identity))

    def set_enabled(self, enabled):
        if self.closed:
            raise PkError("连续 PK 状态读取已关闭")
        if self.busy:
            raise PkError("正在读取或更新连续 PK 状态")
        if self.status is None:
            raise PkError("请先读取连续 PK 状态")
        if self.status.button_disabled:
            raise PkError(self.status.toast or "当前暂不可更改连续 PK 开关")
        worker = UpdateContinuousPkWorker(
            CallbackPresenter(finished=lambda status: self._loaded(status, check_requeue=False),
                        failed=self._failed),
            self.identity, self.kind, enabled, trace_id=self.trace_id)
        self.busy = True
        self._submit(worker)

    def _loaded(self, status, *, check_requeue):
        if self.closed:
            return
        self.busy, self.status = False, status
        self.session._continuous_loaded(status)
        if not self.closed and check_requeue:
            self.session._continuous_requeue(status)

    def _failed(self, error):
        if self.closed:
            return
        self.busy = False
        self.session._continuous_failed(error)

    def _submit(self, worker):
        worker.request_allowed = lambda: not self.closed
        try:
            self.manager.submit(worker)
        except Exception as error:
            self._failed(error)
