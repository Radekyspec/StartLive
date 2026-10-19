from startlive.core.constant.pk import NativePkType
from startlive.core.exceptions import PkError
from startlive.core.pk.trace_id import new_trace_id
from startlive.core.workers.pk.fetch_continuous_status import \
    FetchContinuousPkStatusWorker
from startlive.core.workers.pk.update_continuous import UpdateContinuousPkWorker
from .pk_presenter import PkPresenter


class PkContinuousController:
    """Read the server switch back after updates; never invent local requeue."""

    def __init__(self, manager, identity, kind, *, changed, failed,
                 trace_id=None, requeue_checked=None):
        if kind not in (NativePkType.DOUBLE_CLASSIC,
                        NativePkType.DOUBLE_RANDOM):
            raise PkError("该模式尚未接入连续 PK 开关")
        self.manager, self.identity, self.kind = manager, identity, kind
        self.changed, self.failed = changed, failed
        self.requeue_checked = requeue_checked
        self.trace_id = trace_id or new_trace_id()
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
        self._read(check_requeue=check_requeue)

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
            PkPresenter(finished=lambda _: self._read(), failed=self._failed),
            self.identity, self.kind, enabled, trace_id=self.trace_id)
        self.busy = True
        self._submit(worker)

    def _read(self, *, check_requeue=False):
        self._submit(FetchContinuousPkStatusWorker(
            PkPresenter(finished=lambda status: self._loaded(status,
                                                             check_requeue=check_requeue),
                        failed=self._failed), self.identity))

    def _loaded(self, status, *, check_requeue):
        self.busy, self.status = False, status
        self.changed(status)
        if check_requeue and self.requeue_checked:
            self.requeue_checked(status)

    def _failed(self, error):
        self.busy = False
        self.failed(error)

    def _submit(self, worker):
        worker.request_allowed = lambda: not self.closed
        try:
            self.manager.submit(worker)
        except Exception as error:
            self._failed(error)
