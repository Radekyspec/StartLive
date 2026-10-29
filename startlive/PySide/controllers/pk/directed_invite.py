from startlive.core.constant.pk import NativePkType, PkPhase
from startlive.core.exceptions import PkError
from startlive.core.pk.states.candidates import PkCandidate
from startlive.core.pk.trace import pk_trace
from startlive.core.workers.pk.cancel_invitation import PkCancelInvitationWorker
from startlive.core.workers.pk.invite import PkInviteWorker
from startlive.core.workers.pk.precheck import PkPrecheckWorker
from .request_attempt import RequestAttempt


class PkDirectedInviteController:
    """Verified selected-candidate -> precheck -> outgoing invitation segment.

    The owning session must establish push authorization before calling invite.
    Success means the request was accepted, not that the peer joined or that
    RTC is ready. Accept/end/RTC orchestration remains with that session.
    """

    def __init__(self, session):
        self.session = session
        self.manager, self.identity = session.manager, session.identity
        self.phase = PkPhase.IDLE
        self.trace_id = ""
        self.candidate = None
        self.attempt = RequestAttempt()

    def invite(self, candidate: PkCandidate, *, trace_id):
        if self.phase not in (PkPhase.IDLE, PkPhase.FAILED, PkPhase.FINISHED):
            raise PkError("已有视频 PK 邀请正在处理")
        self.candidate = candidate
        self.attempt.invalidate()
        self.trace_id = trace_id
        self.phase = PkPhase.PREPARING
        self.attempt.inflight, self.attempt.cancel_requested = True, False
        presenter = self._presenter(self._prechecked, self._failed)
        self.attempt.submit(self.manager, PkPrecheckWorker(presenter, self.identity,
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

    def _prechecked(self, result=None):
        self.attempt.inflight = False
        if self.phase is not PkPhase.PREPARING:
            return
        if self.attempt.cancel_requested:
            self._cancelled()
            return
        if result is not None:
            self.phase = PkPhase.IDLE
            self.session._intercepted(result)
            return
        self.phase, self.attempt.inflight = PkPhase.INVITING, True
        presenter = self._presenter(self._sent, self._failed)
        self.attempt.submit(self.manager, PkInviteWorker(presenter, self.identity, self.candidate))

    def _sent(self, result=None):
        # Remain INVITING until the owning session receives a confirmed event.
        self.attempt.inflight = False
        if self.phase is not PkPhase.INVITING:
            return
        if self.attempt.cancel_requested:
            self._send_cancel()
        else:
            self.session._waiting()

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
        self.attempt.submit(self.manager, PkCancelInvitationWorker(
            self._presenter(lambda _=None: self._cancelled(), self._cancel_failed),
            self.identity, self.candidate.uid, trace_id=self.trace_id))

    def _cancelled(self):
        self.attempt.inflight = False
        if self.phase is PkPhase.CONNECTING:
            return
        self.phase, self.attempt.cancel_requested = PkPhase.FINISHED, False
        self.session._cancelled()

    def _cancel_failed(self, error):
        self.attempt.inflight = False
        if self.phase is PkPhase.CONNECTING:
            return
        self.phase = PkPhase.INVITING
        self.session._flow_failed(error)

    def _failed(self, error):
        self.attempt.inflight = False
        if self.phase is PkPhase.CONNECTING:
            return
        self.phase = PkPhase.FAILED
        self.session._flow_failed(error)
