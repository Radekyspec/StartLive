from startlive.core.constant.pk import NativePkType, PkPhase
from startlive.core.exceptions import PkError
from startlive.core.pk.states.candidates import PkCandidate
from startlive.core.pk.trace import pk_trace
from startlive.core.pk.trace_id import new_trace_id
from startlive.core.workers.pk.cancel_invitation import PkCancelInvitationWorker
from startlive.core.workers.pk.invite import PkInviteWorker
from startlive.core.workers.pk.precheck import PkInvitePrecheckWorker
from .request_attempt import RequestAttempt


class PkDirectedInviteController:
    """Verified selected-candidate -> precheck -> outgoing invitation segment.

    The owning session must establish push authorization before calling invite.
    Success means the request was accepted, not that the peer joined or that
    RTC is ready. Accept/end/RTC orchestration remains with that session.
    """

    def __init__(self, manager, identity, *, sent, failed, intercepted,
                 cancelled=None):
        self.manager, self.identity = manager, identity
        self.sent, self.failed, self.intercepted = sent, failed, intercepted
        self.cancelled = cancelled
        self.phase = PkPhase.IDLE
        self.trace_id = ""
        self.candidate = None
        self.attempt = RequestAttempt()

    def invite(self, candidate, *, trace_id=None):
        if not isinstance(candidate, PkCandidate):
            raise PkError("请先搜索并选择视频 PK 对手")
        if self.phase not in (PkPhase.IDLE, PkPhase.FAILED, PkPhase.FINISHED):
            raise PkError("已有视频 PK 邀请正在处理")
        self.candidate = candidate
        self.attempt.invalidate()
        self.trace_id = trace_id or new_trace_id()
        self.phase = PkPhase.PREPARING
        self.attempt.inflight, self.attempt.cancel_requested = True, False
        presenter = self._presenter(self._prechecked, self._failed)
        self._submit(PkInvitePrecheckWorker(presenter, self.identity,
                                            NativePkType.DOUBLE_INVITE,
                                            trace_id=self.trace_id))

    def _presenter(self, finished, failed):
        return self.attempt.presenter(finished, failed, stale=self._stale_reply)

    def _stale_reply(self, serial):
        pk_trace("invite.reply_ignored", trace_id=self.trace_id,
                 uid=self.identity.uid,
                 room_id=self.identity.room_id, attempt_serial=serial,
                 current_attempt_serial=self.attempt.serial,
                 reason="retired_attempt")

    def retire(self):
        """Invalidate HTTP callbacks before local terminal/owner cleanup."""
        self.attempt.invalidate()
        self.phase = PkPhase.FINISHED
        self.attempt.inflight = self.attempt.cancel_requested = False

    def _submit(self, worker):
        self.attempt.submit(self.manager, worker)

    def _prechecked(self, result):
        self.attempt.inflight = False
        if self.phase is not PkPhase.PREPARING:
            return
        if self.attempt.cancel_requested:
            self._cancelled()
            return
        if result.intercepted:
            self.phase = PkPhase.IDLE
            self.intercepted(result)
            return
        self.phase, self.attempt.inflight = PkPhase.INVITING, True
        presenter = self._presenter(self._sent, self._failed)
        self._submit(PkInviteWorker(presenter, self.identity, self.candidate))

    def _sent(self, result):
        # Remain INVITING until the owning session receives a confirmed event.
        self.attempt.inflight = False
        if self.phase is not PkPhase.INVITING:
            return
        if self.attempt.cancel_requested:
            self._send_cancel()
        else:
            self.sent(result)

    def cancel(self):
        if self.phase not in (PkPhase.PREPARING, PkPhase.INVITING):
            raise PkError("当前不在等待邀请结果的阶段")
        self.attempt.cancel_requested = True
        if not self.attempt.inflight:
            self._send_cancel()

    def handoff(self):
        """The owner calls this after a verified matching JOIN event."""
        if self.phase not in (PkPhase.INVITING, PkPhase.STOPPING):
            raise PkError("当前不在等待邀请结果的阶段")
        self.attempt.invalidate()
        self.phase = PkPhase.CONNECTING
        self.attempt.inflight = self.attempt.cancel_requested = False

    def _send_cancel(self):
        self.phase, self.attempt.inflight = PkPhase.STOPPING, True
        self._submit(PkCancelInvitationWorker(
            self._presenter(lambda _: self._cancelled(), self._cancel_failed),
            self.identity, self.candidate.uid, trace_id=self.trace_id))

    def _cancelled(self):
        self.attempt.inflight = False
        if self.phase is PkPhase.CONNECTING:
            return
        self.phase, self.attempt.cancel_requested = PkPhase.FINISHED, False
        if self.cancelled:
            self.cancelled()

    def _cancel_failed(self, error):
        self.attempt.inflight = False
        if self.phase is PkPhase.CONNECTING:
            return
        self.phase = PkPhase.INVITING
        self.failed(error)

    def _failed(self, error):
        self.attempt.inflight = False
        if self.phase is PkPhase.CONNECTING:
            return
        self.phase = PkPhase.FAILED
        self.failed(error)
