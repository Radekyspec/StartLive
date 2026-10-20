from startlive.core.constant.pk import NativePkType, PkPhase
from startlive.core.exceptions import PkError
from startlive.core.pk.trace_id import new_trace_id
from startlive.core.workers.pk.cancel_match import PkCancelMatchWorker
from startlive.core.workers.pk.match import PkMatchWorker
from startlive.core.workers.pk.precheck import PkMatchPrecheckWorker
from .request_attempt import RequestAttempt


class PkMatchController:
    """Classic/random-video matchmaking; media belongs to the owning session."""

    def __init__(self, manager, identity, kind, *, waiting, cancelled, failed,
                 intercepted):
        if kind not in (NativePkType.DOUBLE_CLASSIC,
                        NativePkType.DOUBLE_RANDOM):
            raise PkError("该类型尚未接入随机 PK 流程")
        self.manager, self.identity, self.kind = manager, identity, kind
        self.waiting, self.cancelled, self.failed, self.intercepted = waiting, cancelled, failed, intercepted
        self.phase = PkPhase.IDLE
        self.trace_id = ""
        self.attempt = RequestAttempt()

    def start(self, *, trace_id=None):
        if self.phase not in (PkPhase.IDLE, PkPhase.FINISHED, PkPhase.FAILED):
            raise PkError("已有 PK 匹配正在处理")
        self.trace_id = trace_id or new_trace_id()
        self.attempt.invalidate()
        self.phase = PkPhase.PREPARING
        self.attempt.inflight, self.attempt.cancel_requested = True, False
        self._submit(PkMatchPrecheckWorker(
            self._presenter(finished=self._prechecked, failed=self._failed),
            self.identity,
            self.kind, trace_id=self.trace_id))

    def _presenter(self, *, finished, failed):
        return self.attempt.presenter(finished, failed)

    def _submit(self, worker):
        self.attempt.submit(self.manager, worker)

    def start_continuous(self, *, trace_id):
        """Contract27 caller has checked both-idle/status2/effect2/eligibility."""
        if self.kind != NativePkType.DOUBLE_RANDOM:
            raise PkError("仅视频随机 PK 支持此连续匹配路径")
        if self.phase not in (PkPhase.IDLE, PkPhase.FINISHED, PkPhase.FAILED):
            raise PkError("已有 PK 匹配正在处理")
        self.trace_id = trace_id
        self.attempt.invalidate()
        self.phase, self.attempt.inflight, self.attempt.cancel_requested = PkPhase.MATCHING, True, False
        self._submit(PkMatchWorker(
            self._presenter(finished=self._matched, failed=self._failed),
            self.identity, self.kind, trace_id=trace_id))

    def _prechecked(self, result):
        self.attempt.inflight = False
        if self.phase is not PkPhase.PREPARING:
            return
        if self.attempt.cancel_requested:
            self._cancelled()
        elif result.intercepted:
            self.phase = PkPhase.IDLE
            self.intercepted(result)
        else:
            self.phase, self.attempt.inflight = PkPhase.MATCHING, True
            self._submit(PkMatchWorker(
                self._presenter(finished=self._matched, failed=self._failed),
                self.identity,
                self.kind, trace_id=self.trace_id))

    def _matched(self, result):
        self.attempt.inflight = False
        # A confirmed event can hand ownership to the session before this HTTP
        # callback arrives. Do not then cancel an already-established PK.
        if self.phase is not PkPhase.MATCHING:
            return
        if self.attempt.cancel_requested:
            self._send_cancel()
        else:
            self.waiting(result)

    def cancel(self):
        if self.phase not in (PkPhase.PREPARING, PkPhase.MATCHING):
            raise PkError("当前不在匹配阶段，不能发送取消匹配请求")
        self.attempt.cancel_requested = True
        if not self.attempt.inflight:
            self._send_cancel()

    def handoff(self):
        """Only the owning session's verified pairing event may call this."""
        if self.phase not in (PkPhase.MATCHING, PkPhase.STOPPING):
            raise PkError("当前不在等待匹配结果的阶段")
        self.phase = PkPhase.CONNECTING
        self.attempt.cancel_requested = False

    def retire(self):
        """Retire this flow: discard callbacks and block queued sends."""
        self.attempt.invalidate()
        self.phase = PkPhase.FINISHED
        self.attempt.inflight = self.attempt.cancel_requested = False

    def match_timed_out(self):
        """The owner has accepted Contract43's matching-state/family guard."""
        self.attempt.invalidate()
        self.phase = PkPhase.FINISHED
        self.attempt.inflight = self.attempt.cancel_requested = False

    def observe_server_matching(self):
        """Classic current-info confirms server matching; send no new join."""
        if self.kind != NativePkType.DOUBLE_CLASSIC:
            raise PkError("此状态同步仅适用于经典 PK")
        if self.phase in (PkPhase.MATCHING,
                          PkPhase.STOPPING) or self.attempt.cancel_requested:
            return
        self.attempt.invalidate()
        self.phase = PkPhase.MATCHING
        self.attempt.inflight = self.attempt.cancel_requested = False

    def _send_cancel(self):
        self.phase, self.attempt.inflight = PkPhase.STOPPING, True
        self._submit(PkCancelMatchWorker(
            self._presenter(finished=lambda _: self._cancelled(),
                            failed=self._cancel_failed),
            self.identity, self.kind, trace_id=self.trace_id))

    def _cancelled(self):
        if self.phase in (PkPhase.CONNECTING, PkPhase.FINISHED):
            self.attempt.inflight = False
            return
        self.phase, self.attempt.inflight, self.attempt.cancel_requested = PkPhase.FINISHED, False, False
        self.cancelled()

    def _cancel_failed(self, error):
        # Keep cancellation available: an HTTP error does not prove the server
        # removed this account from its matchmaking queue.
        self.attempt.inflight = False
        if self.phase in (PkPhase.CONNECTING, PkPhase.FINISHED):
            return
        self.phase = PkPhase.MATCHING
        self.failed(error)

    def _failed(self, error):
        if self.phase in (PkPhase.CONNECTING, PkPhase.FINISHED):
            self.attempt.inflight = False
            return
        self.phase, self.attempt.inflight = PkPhase.FAILED, False
        self.failed(error)
