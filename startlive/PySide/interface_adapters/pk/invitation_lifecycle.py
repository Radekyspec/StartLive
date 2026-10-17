"""Incoming prompt lifetime and outgoing invitation results on the GUI dispatcher."""
from math import ceil

from .directed_invite import PkDirectedInviteController
from startlive.core.constant.pk import NativeInteractionState, NativePkType, \
    PkMode, PkPhase
from startlive.core.constant.pk_info import NativePkState
from startlive.core.exceptions import PkError
from startlive.core.pk.events import invitation_context_from_event
from startlive.core.pk.video_eligibility import invitation_eligibility


class PkInvitationLifecycle:
    def __init__(self, session):
        self.session = session
        self.pending = self.accepted = None
        self.deadline = self.remaining = None

    @property
    def idle(self):
        """An unclaimed listener can be replaced by an explicit outgoing flow."""
        session = self.session
        return (
                    session.invitation_only and session.started and not session.closed and not session.stopping
                    and not session._business_started and self.pending is None
                    and self.accepted is None and not session.handle.busy
                    and session.rtc.future is None and session.rtc.event is None
                    and session.join.native_state == NativeInteractionState.READY
                    and session.round_state.state == NativePkState.IDLE
                    and session.flow.phase in (PkPhase.IDLE, PkPhase.FINISHED))

    def set_reception(self, enabled):
        """Local presentation preference; no server-setting or RTC side effect."""
        session = self.session
        if type(enabled) is not bool:
            raise PkError("邀请接收状态必须是开或关")
        if session.closed:
            return
        session.invitation_display_allowed = enabled
        session._trace("session.invitation.reception_changed", enabled=enabled)
        if not enabled:
            self.dismiss()
        self.refresh_activity()
        if self.idle and session._push_authenticated:
            session._status(
                "正在等待视频 PK 邀请…" if enabled else "已暂停接收视频 PK 邀请")

    def refresh_activity(self):
        session = self.session
        if not session.invitation_only or not session.started or session.closed:
            return
        idle = self.idle
        session.view.set_active(not idle)
        session.view.set_invitation_waiting(
            idle and session.invitation_display_allowed)

    def answer(self, event, accept, *, _provider_checked=False):
        session = self.session
        if not _provider_checked:
            session._trace("session.invitation.answer", accept=accept,
                           peer_search=event.peer_search,
                           initiator=event.initiator,
                           invitation_biz_session_id=event.biz_session_id)
        if session.closed or session.stopping or event is not self.pending:
            session._trace("session.invitation.answer_ignored",
                           reason="not_current_pending_invitation")
            return
        session.identity_guard(session.identity)
        if self.tick():
            return
        if not self.can_answer():
            raise PkError("当前已有 PK 操作，不能处理另一条邀请")
        eligibility = invitation_eligibility(session._video_facts())
        if accept:
            if eligibility.allowed is not True:
                self.dismiss()
                raise PkError(eligibility.reason)
            if not _provider_checked:
                def failed(error):
                    if event is self.pending:
                        self.dismiss()
                        session._error(error)

                session._status("正在检查视频 PK 组件…")
                session._check_provider(
                    lambda: self.answer(event, True, _provider_checked=True),
                    failed)
                return
            context = invitation_context_from_event(event)
            session.exit.retire()
            session.expected_peer_uid = context.selected_peer_uid
            self.accepted = event
            session.presentation.info = None
            session.presentation.ended = False
            session._business_started = True
            session.kind = session.round_state.kind = NativePkType.DOUBLE_INVITE
            session.round_state.biz_session_id = context.biz_session_id
            session.presentation.render()
            session.view.set_invitation_waiting(False)
            session._status("正在接受视频 PK 邀请…")
        # Native closes the prompt when Handle1 is issued, without waiting for
        # HTTP. Keep the accepted snapshot separate for a later HTTP/push JOIN.
        self.dismiss(refresh=False)
        if session.invitation_only:
            session.view.set_active(True)
            session.view.set_invitation_waiting(False)
        try:
            session.handle.handle_event(event, accept=accept,
                                        eligibility=eligibility)
        except Exception as error:
            self.failed(error)
        finally:
            self.refresh_activity()

    def can_answer(self):
        # An outgoing owner can still be locally idle while its initial
        # continuous-status request is pending. Only the reception owner may
        # accept another flow; the user's outgoing action already owns this one.
        session = self.session
        return (session.invitation_only and session.invitation_display_allowed
                and session._push_authenticated and not session.closed
                and not session.stopping and not session._business_started and not session.handle.busy
                and session.rtc.future is None and session.join.native_state == NativeInteractionState.READY
                and session.round_state.state == NativePkState.IDLE
                and session.flow.phase in (PkPhase.IDLE, PkPhase.FINISHED))

    def dismiss(self, *, refresh=True):
        session = self.session
        pending, self.pending = self.pending, None
        self.deadline = self.remaining = None
        if pending is not None:
            session.view.dismiss_invitation()
        if refresh:
            self.refresh_activity()

    def tick(self):
        """Return true only when this tick expires the pending presentation."""
        session = self.session
        if self.pending is None or self.deadline is None:
            return False
        remaining = max(0, ceil(self.deadline - session._clock()))
        if remaining == 0:
            session._trace("session.invitation.expired",
                           initiator=self.pending.initiator)
            self.dismiss()
            session._status("邀请已过期，继续等待视频 PK 邀请…")
            return True
        if remaining != self.remaining:
            self.remaining = remaining
            session.view.set_invitation_remaining(remaining)
        return False

    def finish_outgoing(self, event):
        """Contract50 source7 sender result; never an HTTP/RTC quit request."""
        session = self.session
        reason = None
        if event.source != 7 or event.action_type != 1:
            reason = "unsupported_outgoing_result"
        elif (
                not session._push_authenticated or not session._business_started or session.invitation_only
                or session.options.mode != PkMode.VIDEO or not isinstance(
            session.flow, PkDirectedInviteController)
                or session.round_state.kind != NativePkType.DOUBLE_INVITE):
            reason = "not_outgoing_directed_owner"
        elif (session.flow.phase not in (PkPhase.INVITING, PkPhase.STOPPING)
              or session.round_state.state != NativePkState.STARTING
              or session.rtc.event is not None or session.rtc.future is not None
              or session.join.native_state != NativeInteractionState.READY):
            # PREPARING has not sent an invitation. JOIN/round handoff wins
            # over a later pending-result notification for the same peer.
            reason = "not_pending_outgoing_invitation"
        peer_search = event.target_uid if event.operation_type == 2 else event.operator_uid
        if reason is None and (
                peer_search is None or peer_search <= 0 or session.flow.candidate is None
                or peer_search != session.flow.candidate.uid):
            reason = "different_invited_uid"
        known_session = session.round_state.biz_session_id or (
            session.round_state.info.basic.biz_session_id if session.round_state.info is not None else "")
        if reason is None and known_session and event.biz_session_id != known_session:
            # Optional stronger StartLive ownership, not the native UID key.
            reason = "different_invitation_session"
        if reason is not None:
            session._trace("session.outgoing_invitation.ignored", reason=reason,
                           operation_type=event.operation_type,
                           action_type=event.action_type,
                           source=event.source, result_peer_uid=peer_search,
                           expected_peer_uid=session.expected_peer_uid)
            return False

        # Invalidate first: an in-flight success/failure/deferred cancel must
        # not restore this attempt while observers update their displays.
        session.flow.retire()
        session._polling_suspended = True
        session.round.stop_polling()
        session._trace("session.outgoing_invitation.finished",
                       operation_type=event.operation_type,
                       source=event.source, result_peer_uid=peer_search,
                       reason="refused" if event.operation_type == 2 else "timed_out")
        session.round_state.quit_round()
        session.round_state.info = None
        session._round_finished(event)
        session._status(
            "对方已拒绝 PK 邀请" if event.operation_type == 2 else "PK 邀请已超时")
        # No RTC exists here. Retiring the local owner stops push reception
        # and rejects late JOIN/PK_INFO; a new UI attempt gets a new owner.
        session.close()
        return True

    def cancel_pending(self, event):
        session = self.session
        invite = self.pending
        if (invite is None or invite.source not in (5,
                                                    7) or event.source != invite.source
                or event.operation_type != 3 or event.action_type != 1
                or not event.operator_uid or event.operator_uid <= 0
                or event.operator_uid != invite.initiator):
            session._trace("session.operation.ignored",
                           operation_type=event.operation_type,
                           action_type=event.action_type, source=event.source,
                           operator_uid=event.operator_uid,
                           reason="not_current_pending_cancel")
            return
        # Stronger StartLive binding: when either message supplies a business
        # session, both must supply the same value. Native source5/7 only checks
        # the original initiator, which is distinct from the Handle peer UID.
        if ((invite.biz_session_id or event.biz_session_id)
                and invite.biz_session_id != event.biz_session_id):
            session._trace("session.operation.ignored",
                           reason="different_invitation_session",
                           event_biz_session_id=event.biz_session_id)
            return
        session._trace("session.invitation.cancelled_by_peer",
                       operator_uid=event.operator_uid)
        self.dismiss()
        session._status("对方已取消邀请，继续等待视频 PK 邀请…")

    def handled(self, _):
        session = self.session
        if session.closed:
            return
        self.dismiss()
        session._trace("session.invitation.handled",
                       accepted=self.accepted is not None,
                       rtc_started=session.rtc.future is not None)
        if self.accepted is None:
            session._status(
                "已拒绝邀请，继续等待视频 PK 邀请…" if session.invitation_display_allowed else
                "已拒绝邀请，已暂停接收视频 PK 邀请")
        elif session.rtc.future is None:
            session._status("已接受邀请，正在等待视频连线…")

    def failed(self, error):
        session = self.session
        if session.closed:
            return
        try:
            session.identity_guard(session.identity)
        except Exception as identity_error:
            session._fatal(identity_error)
            return
        self.dismiss()
        if session.rtc.future is None:
            self.accepted = None
            session.expected_peer_uid = None
            session._business_started = False
            session.round_state.biz_session_id = ""
            self.refresh_activity()
        session._error(error)

    def show_outgoing_acceptance(self, event):
        """Presentation only; acceptance never supplies or constrains a JOIN.

        Ordinary directed PK joins with the server-provided ticket (push or
        HTTP). Missing JOIN is a reception issue, not a reason to fetch a ticket.
        """
        session = self.session
        session._trace("session.operation.observed",
                       operation_type=event.operation_type,
                       action_type=event.action_type, source=event.source,
                       rtc_started=session.rtc.future is not None)
        if (
                session.invitation_only or not session._business_started or not session._push_authenticated
                or session.kind != NativePkType.DOUBLE_INVITE or session.options.mode != PkMode.VIDEO
                or session.rtc.event is not None or session.rtc.future is not None
                or session._polling_suspended or session.presentation.ended or session.exit.busy
                or session.flow.phase not in (PkPhase.INVITING,
                                              PkPhase.CONNECTING)
                or session.round_state.state in (NativePkState.IDLE,
                                                 NativePkState.EXIT,
                                                 NativePkState.END)):
            return
        peer_search = session.expected_peer_uid
        data = event.raw.get("data", {})
        if (
                event.source != 7 or event.action_type != 1 or event.own_side is not False
                or type(peer_search) is not int or peer_search <= 0
                or not event.operator_uid == event.target_uid == event.peer_search == peer_search
                or not isinstance(data, dict) or data.get(
            "biz_label") != "universal_multi_conn"):
            return
        known_session = session.round_state.biz_session_id
        if known_session and event.biz_session_id != known_session:
            return
        session._trace("session.outgoing.accepted", peer_search=peer_search,
                       event_biz_session_id=event.biz_session_id,
                       event_rtc_channel_id=event.rtc_channel_id)
        session._status("对方已接受，等待视频连线通知…")

    def resume_waiting(self):
        session = self.session
        if not session.invitation_only or session.closed or not session._both_idle():
            return
        self.dismiss()
        self.accepted = None
        session.expected_peer_uid = None
        session._business_started = False
        session.round_state.biz_session_id = ""
        session._trace("session.invitation.listening_resumed",
                       enabled=session.invitation_display_allowed)
        self.refresh_activity()
        session._status(
            "正在等待视频 PK 邀请…" if session.invitation_display_allowed else
            "已暂停接收视频 PK 邀请")

    def present(self, event):
        session = self.session
        eligibility = invitation_eligibility(session._video_facts())
        context = invitation_context_from_event(event)
        # Source12 requires a separate room context. Listening never
        # cancels an outgoing request or auto-rejects a hidden invite.
        if (self.can_answer() and self.pending is None
                and context.source in (5, 7, 10, 11)
                and context.selected_peer_uid > 0
                and eligibility.allowed is True):
            # StartLive presentation policy: only an explicit positive
            # int32 number of seconds permits an actionable prompt.
            # Missing/invalid/negative durations do not invent a server
            # deadline; zero is immediately unavailable. No Handle2.
            duration = event.invitation_timeout
            if type(duration) is not int or not 0 < duration < 1 << 31:
                session._trace("session.invitation.ignored",
                               reason="unavailable_duration",
                               invitation_timeout=duration)
                session._status("邀请已过期，继续等待…" if duration == 0 else
                                "邀请缺少有效的等待时长，继续等待…")
                return
            self.pending = event
            self.refresh_activity()
            session._trace("session.invitation.presented",
                           peer_search=context.peer_search,
                           initiator=event.initiator, source=context.source,
                           invitation_biz_session_id=context.biz_session_id,
                           invitation_timeout=duration)
            session.view.show_invitation(event)
            # Countdown starts when this item becomes the current
            # prompt, not at server send time or receipt in a queue.
            self.deadline = session._clock() + duration
            self.tick()
        else:
            session._trace("session.invitation.ignored",
                           reason="not_eligible_or_busy",
                           source=context.source, eligible=eligibility.allowed,
                           eligibility_reason=eligibility.reason,
                           pending=self.pending is not None)
