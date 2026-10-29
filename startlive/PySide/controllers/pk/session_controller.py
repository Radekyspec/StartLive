"""One account/flow owner, driven entirely on the GUI dispatcher."""
from time import monotonic

from startlive.core.constant.pk import NativeInteractionState, NativePkType, \
    PkMode, PkPhase
from startlive.core.constant.pk_api import PK_CLASSIC_INFO_UNAVAILABLE
from startlive.core.constant.pk_info import NativePkState, PkInfoAction
from startlive.core.exceptions import PkError
from startlive.core.pk.identity import require_current_identity
from startlive.core.pk.pk_eligibility import pk_start_block_reason
from startlive.core.pk.pk_info import parse_pk_info
from startlive.core.pk.round_state import PkRoundState
from startlive.core.pk.states.eligibility import PkStartEligibilityState, \
    PkVideoEligibilityState
from startlive.core.pk.states.events import (
    PkBattleEndEvent,
    PkBattlePreEvent,
    PkBattleStartEvent,
    PkInfoEvent,
    PkInfoHintEvent,
    PkInvitationEvent,
    PkJoinEvent,
    PkLeaveEvent,
    PkMatchTimeoutEvent,
    PkOperationEvent,
    PkStreamControlEvent,
)
from startlive.core.pk.states.info import PkClassicInfoResult, PkInfoDecision
from startlive.core.pk.trace import pk_trace
from startlive.core.pk.trace_id import new_trace_id
from startlive.core.pk.video_eligibility import video_block_reason
from .continuous_controller import PkContinuousController
from .directed_invite import PkDirectedInviteController
from .exit_controller import PkExitController
from .match_controller import PkMatchController
from startlive.core.danmaku.connection import DanmakuConnection
from startlive.core.workers.pk.push import PkPushWorker
from .round_controller import PkRoundController
from .round_presentation import PkRoundPresentation


class _Jobs:
    """Track a flow's jobs without creating another thread pool or dispatcher."""

    def __init__(self, manager):
        self.manager = manager
        self.futures = []
        self.retired = False

    def submit(self, worker, **kwargs):
        if self.retired:
            raise PkError("PK 会话已关闭")
        self.futures = [future for future in self.futures if not future.done()]
        future = self.manager.submit(worker, **kwargs)
        self.futures.append(future)
        return future

    @property
    def busy(self):
        return any(not future.done() for future in self.futures)


class PkSessionController:
    def __init__(self, view, identity, options, *, invitation_display_allowed=False,
                 invitation_only=False):
        manager = _Jobs(view._workers)
        self.manager, self.identity, self.options, self.view = manager, identity, options, view
        self.invitation_only = invitation_only
        self.invitation_display_allowed = invitation_display_allowed or invitation_only
        self._push_authenticated = False
        self.trace_id = new_trace_id()
        self.expected_peer_uid = options.peer_search
        self.kind = (
            NativePkType.DOUBLE_CLASSIC if options.mode == PkMode.TRADITIONAL else
            NativePkType.DOUBLE_INVITE if options.peer_search is not None or options.mode == PkMode.VIDEO_LINK else NativePkType.DOUBLE_RANDOM)
        self.closed = self.stopping = self.started = False
        self._business_started = self._continuous_written = False
        self._continuous_refresh_pending = False
        self._polling_suspended = False
        self._exit_query_resume_pending = False
        self._rtc_leave_deadline = None
        self._pending_round_events = []
        self.invitations = self.rtc = self.handle = None
        if options.mode != PkMode.TRADITIONAL:
            self._initialize_rtc()
        self.presentation = PkRoundPresentation(self)
        self.round_state = PkRoundState(self.kind)
        self.round = PkRoundController(self)
        self.exit = PkExitController(self)
        if options.mode == PkMode.VIDEO_LINK:
            from .video_link_controller import PkVideoLinkController
            self.flow = PkVideoLinkController(self)
        elif self.kind == NativePkType.DOUBLE_INVITE:
            self.flow = PkDirectedInviteController(self)
        else:
            self.flow = PkMatchController(self)
        # Continuous PK is a video-PK server setting only. Classic has no
        # verified auto-next behavior and no writable switch, so it must not
        # create a reader or issue autoMatchSwitchStatus at all.
        self.continuous = (
            PkContinuousController(self)
            if not invitation_only and options.mode == PkMode.VIDEO else None)
        self.push = DanmakuConnection(manager, identity, ready=self._push_ready,
                                 event=self.receive,
                                 failed=self._fatal, push_factory=PkPushWorker)
        self._trace("session.created", mode=options.mode,
                    invitation_only=invitation_only,
                    requested_peer_uid=options.peer_search,
                    continuous=options.continuous)

    def _initialize_rtc(self):
        from .invitation_lifecycle import PkInvitationLifecycle
        from .rtc_lifecycle import PkRtcLifecycle
        from .handle_controller import PkHandleController

        if self.options.mode != PkMode.TRADITIONAL:
            self.invitations = PkInvitationLifecycle(self)
        self.rtc = PkRtcLifecycle(self)
        if self.invitations is not None:
            self.handle = PkHandleController(self)

    def _join_block_reason(self, event):
        if self.options.mode == PkMode.TRADITIONAL:
            facts = self.view._output_readiness(PkMode.TRADITIONAL)
            if (event.biz_label == "classic_pk" and facts.output_ready is True
                    and facts.live_output_active is True):
                return None
            return "当前不能加入经典 PK 语音"
        if event.biz_label == "classic_pk":
            return "经典语音通知与当前模式不符"
        return video_block_reason(self._video_facts())

    def _stop_rtc(self):
        self._rtc_leave_deadline = None
        if self.rtc is not None:
            self.rtc.stop()

    def _trace(self, event, **fields):
        pk_trace(event, **({"trace_id": self.trace_id, "uid": self.identity.uid,
                            "room_id": self.identity.room_id,
                            "pk_id": self.round_state.round_id,
                            "biz_session_id": self.round_state.biz_session_id,
                            "rtc_channel_id": self.join_event.rtc_channel_id if self.join_event else None,
                            "pk_state": self.round_state.state,
                            "kind": self.round_state.kind,
                            "interaction_state": self.rtc.native_state if self.rtc else None,
                            "phase": self.flow.phase, "closed": self.closed,
                            "stopping": self.stopping} | fields))

    def _status(self, text):
        if not self.closed:
            self.view.set_status(text)

    def _error(self, error):
        self._trace("session.error", error_type=type(error).__name__,
                    error=str(error))
        self._status(str(error))

    def _fatal(self, error):
        self._trace("session.fatal", error_type=type(error).__name__,
                    error=str(error))
        self._error(error)
        self.close()

    def _flow_failed(self, error):
        self._error(error)
        if self.flow.phase == PkPhase.FAILED:
            self.close()
        elif (not self.closed and self._polling_suspended
              and self.flow.phase in (PkPhase.MATCHING, PkPhase.INVITING)):
            # A failed cancel leaves server matching unresolved. Resume the
            # current owner explicitly; retired query callbacks stay retired.
            self._polling_suspended = False
            if isinstance(self.flow, PkMatchController):
                self.round.start_polling()

    def _continuous_failed(self, error):
        if self.closed:
            return
        try:
            require_current_identity(self.identity)
        except Exception as identity_error:
            self._fatal(identity_error)
            return
        self._render_continuous()
        self._error(error)
        if not self._business_started:
            self.close()

    def _render_continuous(self):
        if self.closed or self.continuous is None:
            return
        status = self.continuous.status
        self.view.set_continuous_status(
            status.enabled_for(
                self.continuous.kind) if status is not None else self.options.continuous,
            status is not None and not status.button_disabled and not self.continuous.busy)

    def _start_facts(self):
        facts = self.view._output_readiness(self.options.mode)
        return PkStartEligibilityState(facts.output_ready,
                                       facts.live_output_active,
                                       facts.voice_microphone_available,
                                       self.round_state.state)

    def _video_facts(self):
        facts = self.view._output_readiness(PkMode.VIDEO)
        return PkVideoEligibilityState(facts.output_ready,
                                       facts.live_output_active,
                                       self.rtc.native_state,
                                       2 if self.rtc.event else 0,
                                       self.round_state.state,
                                       self.round_state.kind)

    def start(self):
        self._trace("session.start.requested", mode=self.options.mode,
                    invitation_only=self.invitation_only)
        if self.started or self.closed:
            raise PkError("此 PK 会话已启动或关闭")
        require_current_identity(self.identity)
        if self.invitation_only and (
                self.options.mode == PkMode.TRADITIONAL or self.options.peer_search is not None
                or self.options.continuous):
            raise PkError("等待邀请仅用于未指定对手的视频 PK")
        if self.options.mode == PkMode.TRADITIONAL and self.options.peer_search is not None:
            raise PkError("经典 PK 仅支持随机匹配")
        if self.options.mode == PkMode.TRADITIONAL:
            self.view.require_classic_audio_ready()
        if self.kind == NativePkType.DOUBLE_INVITE and not self.invitation_only:
            if self.options.candidate is None or self.options.candidate.uid != self.options.peer_search:
                raise PkError("请搜索并选择视频 PK 对手")
        blocked_reason = (
            video_block_reason(self._video_facts()) if self.invitation_only else
            pk_start_block_reason(self.kind, self._start_facts()))
        if blocked_reason is not None:
            raise PkError(blocked_reason)
        self.started = True
        self.presentation.render()
        self._render_continuous()
        self.view.set_active(not self.invitation_only)
        if self.invitation_only:
            self.invitations.refresh_activity()
        if self.options.mode != PkMode.TRADITIONAL:
            self._status("正在检查视频 PK 组件…")
            self._check_provider(self._start_push, self._fatal)
        else:
            self._start_push()

    def _check_provider(self, ready, failed):
        def completed():
            if not self.closed:
                require_current_identity(self.identity)
                ready()

        self.view.provider_readiness.ensure(self, completed,
                                       lambda error: failed(
                                           error) if not self.closed else None)

    def _start_push(self):
        if self.closed:
            return
        require_current_identity(self.identity)
        blocked_reason = (
            video_block_reason(self._video_facts()) if self.invitation_only else
            pk_start_block_reason(self.kind, self._start_facts()))
        if blocked_reason is not None:
            raise PkError(blocked_reason)
        self._status("正在连接 PK 消息服务…")
        self._trace("session.push.start")
        self.push.start()

    def _push_ready(self):
        if self.closed:
            return
        try:
            self._push_authenticated = True
            self._trace("session.push.authenticated")
            if self.invitation_only:
                self.invitations.refresh_activity()
                self._status(
                    "正在等待视频 PK 邀请…" if self.invitation_display_allowed else
                    "已暂停接收视频 PK 邀请")
            elif self.continuous:
                self.continuous.load()
            else:
                self._begin_business()
        except Exception as error:
            self._fatal(error)

    def _continuous_loaded(self, status):
        if self.closed:
            return
        try:
            require_current_identity(self.identity)
        except Exception as error:
            self._fatal(error)
            return
        enabled = status.enabled_for(self.continuous.kind)
        self._trace("session.continuous.confirmed", enabled=enabled,
                    status=status.status,
                    pk_versions=status.pk_versions,
                    effect_pk_version=status.effect_pk_version,
                    button_disabled=status.button_disabled)
        self._render_continuous()
        if self._business_started:
            return
        if enabled != self.options.continuous:
            if self._continuous_written:
                self._fatal(PkError("连续 PK 开关未生效，请重新确认"))
                return
            self._continuous_written = True
            try:
                self.set_continuous(self.options.continuous)
            except Exception as error:
                self._fatal(error)
        else:
            self._begin_business()

    def _begin_business(self):
        if self.closed or self._business_started or self.invitation_only:
            return
        require_current_identity(self.identity)
        if self.options.mode == PkMode.TRADITIONAL:
            try:
                self.view.require_classic_audio_ready()
            except Exception as error:
                self._fatal(error)
                return
        blocked_reason = pk_start_block_reason(self.kind, self._start_facts())
        if blocked_reason is not None:
            self._fatal(PkError(blocked_reason))
            return
        self.exit.retire()
        self._business_started = True
        self._trace("session.business.start",
                    requested_peer_uid=self.expected_peer_uid)
        if self.options.mode == PkMode.VIDEO_LINK:
            # PkVideoLinkController.invite() has no trace_id parameter; its
            # Connect worker does not send a client_traceid.
            self.flow.invite(self.options.candidate)
            self.view.refresh_controls()
            return
        self.round_state.state = NativePkState.STARTING
        self.presentation.info = self.presentation.peer_uid = None
        self.presentation.ended = False
        self.presentation.render()
        if self.kind == NativePkType.DOUBLE_INVITE:
            self.flow.invite(self.options.candidate, trace_id=self.trace_id)
        else:
            self.flow.start(trace_id=self.trace_id)
        self.view.refresh_controls()

    def _waiting(self):
        if not self.closed and self.round_state.state == NativePkState.STARTING:
            directed = self.kind == NativePkType.DOUBLE_INVITE
            # Native kind5 start success stays in state1 and notifies
            # substatus3 with the cached DTO. It does not enter matching or
            # consume the response PK_INFO/JOIN/wait_time as another event.
            if not directed:
                self.round_state.state = NativePkState.MATCHING
            if isinstance(self.flow, PkMatchController):
                self.round.start_polling()
            self.presentation.render()
            self._trace("session.business.waiting",
                        requested_peer_uid=self.expected_peer_uid,
                        **({"native_substatus": 3} if directed else {}))
            self._status(
                "等待对方接受邀请…" if self.kind == NativePkType.DOUBLE_INVITE else "正在随机匹配…")

    def _intercepted(self, reason):
        self._trace("session.precheck.intercepted", reason=reason)
        self._status(reason)
        self.close()

    def _cancelled(self):
        self._trace("session.business.cancelled")
        # Native ReqCancelMatch success is followed by QuitPkForce and Idle;
        # no exit/handle/quit request is part of this branch.
        self.round.stop_polling()
        self.round_state.quit_round()
        self._status("已取消 PK")
        self.close()

    def receive(self, event):
        command = getattr(event, "command", type(event).__name__)
        self._trace("session.push.received", command=command,
                    event_pk_id=event.info.basic.pk_id if isinstance(event,
                                                                     PkInfoEvent) else getattr(
                        event, "pk_id", None),
                    event_biz_session_id=getattr(event, "biz_session_id", None),
                    event_rtc_channel_id=getattr(event, "rtc_channel_id", None))
        if self.closed:
            self._trace("session.push.ignored", command=command,
                        reason="owner_closed")
            return
        try:
            require_current_identity(self.identity)
            if isinstance(event, PkBattleEndEvent):
                # The round boundary is local state, independent of RTC. Handle
                # it even while a server 114 is stopping media: either order
                # (dt:33 then 114, or 114 then dt:33) must converge to Idle.
                self.round.handle_event(event)
                return
            if self.stopping:
                # LEAVE and the final PK_INFO can arrive in either order.
                # Keep round updates until local RTC cleanup has completed;
                # replay must not query/requeue while that worker is alive.
                if isinstance(event, PkInfoEvent):
                    self._pending_round_events.append(event)
                    self._trace("session.push.buffered", command=event.command,
                                pending_count=len(self._pending_round_events))
                else:
                    self._trace("session.push.ignored", command=command,
                                reason="rtc_stopping")
                return
            if isinstance(event, PkStreamControlEvent):
                if self.rtc is not None:
                    self.rtc.stream_control(event)
            elif isinstance(event, PkInfoHintEvent):
                self._receive_pk_hint(event)
            elif isinstance(event,
                            PkOperationEvent) and self.options.mode == PkMode.VIDEO_LINK:
                self.flow.operation(event)
            elif isinstance(event, PkJoinEvent):
                if self.options.mode == PkMode.TRADITIONAL and self.rtc is None:
                    if event.biz_label != "classic_pk" or self._join_block_reason(
                            event) is not None:
                        return
                    self._initialize_rtc()
                if self.options.mode == PkMode.VIDEO_LINK:
                    self.flow.join(event)
                    return
                if self.invitation_only and self.invitations.accepted is None:
                    self._trace("session.push.ignored", command=event.command,
                                reason="invitation_not_accepted")
                    return
                if not self.rtc.handle_join(event):
                    self._trace("session.push.ignored", command=event.command,
                                reason="duplicate_or_unusable_join")
            elif isinstance(event, PkLeaveEvent) and self.join_event:
                self.rtc.handle_leave(event)
            elif isinstance(event, PkInfoEvent):
                if self.options.mode == PkMode.VIDEO_LINK:
                    if self.join_event is None or event.info.basic.biz_session_id != self.join_event.biz_session_id:
                        return
                if self.invitation_only and not self._business_started:
                    self._trace("session.push.ignored", command=event.command,
                                reason="listener_has_no_accepted_business")
                    return
                self.round.handle_event(event)
            elif isinstance(event, PkMatchTimeoutEvent):
                if self.round.handle_match_timeout(event) and isinstance(
                        self.flow, PkMatchController):
                    self.flow.match_timed_out()
            elif isinstance(event,
                            PkOperationEvent) and self.invitations is not None:
                if event.operation_type in (2, 4):
                    self.invitations.finish_outgoing(event)
                elif event.operation_type == 3:
                    self.invitations.cancel_pending(event)
                elif event.operation_type == 1:
                    self.invitations.show_outgoing_acceptance(event)
                else:
                    # The traced source7/op1 consumer does not itself
                    # start RTC. It may arrive after JOIN has already started
                    # admission, as in the native 2026-10-14 12:11 trace.
                    self._trace("session.operation.observed",
                                operation_type=event.operation_type,
                                action_type=event.action_type,
                                source=event.source,
                                rtc_started=self.rtc.future is not None)
            elif isinstance(event, (PkBattlePreEvent, PkBattleStartEvent)):
                if self.round_state.kind == NativePkType.DOUBLE_CLASSIC and event.pk_id:
                    if event.pk_id == self.round_state.last_ended_round_id:
                        self._trace("session.push.ignored", command=command,
                                    reason="already_ended",
                                    event_pk_id=event.pk_id)
                    elif self.round_state.round_id in (0, event.pk_id):
                        self.round_state.round_id = event.pk_id
                        self.round.query_classic(event.pk_id)
                    else:
                        self._trace("session.push.ignored",
                                    command=event.command,
                                    reason="different_round")
                else:
                    self._trace("session.push.ignored", command=event.command,
                                reason="not_current_classic_round")
            elif isinstance(event,
                            PkInvitationEvent) and self.options.mode == PkMode.VIDEO:
                self.invitations.present(event)
            else:
                self._trace("session.push.ignored", command=command,
                            reason="no_current_handler")
        except Exception as error:
            self._trace("session.push.failed", command=command,
                        response=getattr(event, "raw", None),
                        error_type=type(error).__name__, error=str(error))
            self._error(error)

    def _receive_pk_hint(self, event):
        """A compact push identifies a round; never reinterpret its status enum."""
        if (self.options.mode == PkMode.TRADITIONAL or self.join_event is None
                or self.closed or self.stopping or self._polling_suspended
                or type(event.pk_id) is not int or not 0 < event.pk_id < 1 << 63
                or event.pk_id == self.round_state.last_ended_round_id
                or (
                        event.biz_session_id and event.biz_session_id != self.join_event.biz_session_id)):
            return
        state = self.round_state
        if state.round_id == event.pk_id:
            return
        if state.round_id and state.state != NativePkState.IDLE:
            self._trace("session.pk_hint.ignored",
                        reason="different_active_round",
                        event_pk_id=event.pk_id)
            return
        self.round.stop_polling()
        state.round_id = event.pk_id
        state.state = NativePkState.PREPARING
        state.timestamp = 0
        state.info = None
        state.biz_session_id = self.join_event.biz_session_id
        self.view.set_active(True)
        self._status("对方已发起 PK，正在读取回合信息…")
        self.round.query_current(event.pk_id)
        self.round.start_polling(resume=True)

    def _round_changed(self, decision):
        if self.closed:
            return
        self.presentation.info, self.presentation.ended = decision.info, False
        self.presentation.render()
        self.view.set_active(True)
        if self.options.mode == PkMode.VIDEO_LINK:
            self.round.start_polling(resume=True)
        if (
                decision.state == NativePkState.MATCHING and self.round_state.kind == NativePkType.DOUBLE_CLASSIC
                and not self._polling_suspended and isinstance(self.flow,
                                                               PkMatchController)
                and self.flow.kind == NativePkType.DOUBLE_CLASSIC):
            self.flow.observe_server_matching()
        elif decision.state >= NativePkState.PREPARING and self.flow.phase in (
                PkPhase.MATCHING, PkPhase.INVITING):
            self.flow.handoff()
        if (self.options.mode == PkMode.VIDEO and self.rtc.event is None
                and decision.state >= NativePkState.PREPARING):
            self._trace("session.rtc.awaiting_join",
                        event_pk_id=decision.info.basic.pk_id,
                        event_biz_session_id=decision.info.basic.biz_session_id,
                        rtc_started=self.rtc.future is not None)
            self._status(
                "PK 房间已建立，尚未收到音视频入房通知，双方音视频未连接")
        else:
            self._status(
                "PK 进行中" if decision.state == NativePkState.PKING else "PK 状态已更新")

    def _round_finished(self, result):
        if not self.closed:
            self._trace("session.round.finished",
                        result_type=type(result).__name__,
                        action=result.action if isinstance(result,
                                                           PkInfoDecision) else None,
                        completed_pk_id=result.info.basic.pk_id if isinstance(
                            result, PkInfoDecision) else None)
            if isinstance(result, PkInfoDecision):
                self.presentation.info = result.info
                self.presentation.ended = (
                        result.action == PkInfoAction.ROUND_ENDED)
            elif not self.presentation.ended:
                # A 6204 current-state reply confirms "no matching round". In
                # the normal end path it arrives after the final score has been
                # shown, so it must not erase that terminal presentation.
                self.presentation.info = None
                self.presentation.ended = False
            self.presentation.render()
            if (isinstance(result,
                           PkClassicInfoResult) and result.code == PK_CLASSIC_INFO_UNAVAILABLE
                    and result.auto_match_status != 2 and isinstance(self.flow,
                                                                     PkMatchController)):
                self.flow.match_timed_out()
            self.view.set_active(False)
            if (isinstance(result, PkInfoDecision)
                    and result.action == PkInfoAction.ROUND_ENDED
                    and self.round_state.kind == NativePkType.DOUBLE_CLASSIC):
                self._arm_rtc_leave_fallback()
            if self.invitations is not None:
                self.invitations.resume_waiting()

    def _refresh_continuous(self):
        # Contract27: round terminal with an active RTC connection does not
        # refresh/requeue. Interaction Ready supplies a separate later trigger.
        if self.closed or not self.continuous or not self._both_idle():
            return
        self._continuous_refresh_pending = self.continuous.busy
        if not self.continuous.busy:
            self.continuous.load(check_requeue=True)
            self._render_continuous()

    def _both_idle(self):
        if self.round_state.state != NativePkState.IDLE or self.stopping:
            return False
        return self.rtc is None or (
                self.rtc.native_state == NativeInteractionState.READY
                and self.rtc.future is None)

    def _arm_rtc_leave_fallback(self):
        """StartLive policy: do not wait forever for a missing server 114.

        The native client has no timeout; a lost LEAVE leaves the old channel
        attached until the next JOIN. This bounded fallback is local cleanup,
        not a PK business request, and is logged separately.
        """
        rtc = self.rtc
        if (self.closed or self.stopping or rtc is None or rtc.event is None
                or rtc.future is None or rtc.future.done()):
            return False
        if self._rtc_leave_deadline is None:
            self._rtc_leave_deadline = monotonic() + 30.0
            self._trace("session.rtc.leave_fallback.armed",
                        timeout=30.0)
        return True

    def _check_rtc_leave_fallback(self):
        deadline = self._rtc_leave_deadline
        if deadline is None or self.closed or self.stopping:
            return False
        rtc = self.rtc
        if (rtc is None or rtc.event is None or rtc.future is None
                or rtc.future.done()):
            self._rtc_leave_deadline = None
            return False
        if monotonic() < deadline:
            return False
        self._rtc_leave_deadline = None
        self._trace("session.rtc.leave_fallback.fired",
                    timeout=30.0,
                    reason="classic_pk_114_not_received")
        rtc.stop()
        return True

    def _continuous_requeue(self, status):
        if (
                self.closed or self.options.mode != PkMode.VIDEO or status.status != 2
                or status.effect_pk_version != 2 or not self._both_idle()):
            return
        require_current_identity(self.identity)
        blocked_reason = pk_start_block_reason(NativePkType.DOUBLE_RANDOM,
                                        self._start_facts(),
                                        continuous_video=True)
        if blocked_reason is not None:
            self._status(blocked_reason)
            return
        self.exit.retire()
        self.round_state.kind = NativePkType.DOUBLE_RANDOM
        self.round_state.state = NativePkState.STARTING
        self.round_state.biz_session_id = ""  # Previous RTC owner was fully retired.
        self.kind = NativePkType.DOUBLE_RANDOM
        self.expected_peer_uid = None
        self.match_source = "continuous_pk"
        self._trace("session.continuous.requeue", status=status.status,
                    effect_pk_version=status.effect_pk_version)
        self._polling_suspended = False
        self.presentation.info = self.presentation.peer_uid = None
        self.presentation.ended = False
        self.presentation.render()
        if not isinstance(self.flow, PkMatchController):
            self.flow = PkMatchController(self.manager, self.identity,
                                          NativePkType.DOUBLE_RANDOM,
                                          waiting=self._waiting,
                                          cancelled=self._cancelled,
                                          failed=self._flow_failed,
                                          intercepted=self._intercepted)
        self.flow.phase = PkPhase.FINISHED
        self.view.set_active(True)
        self._status("正在继续随机匹配…")
        # Same owning flow/trace; the verified native branch skips precheck.
        self.flow.start_continuous(trace_id=self.trace_id)

    def set_continuous(self, enabled):
        self._trace("session.continuous.requested", enabled=enabled)
        if self.closed or self.continuous is None:
            raise PkError("当前模式不可更改连续 PK")
        require_current_identity(self.identity)
        try:
            self.continuous.set_enabled(enabled)
        finally:
            # The checkbox represents the last confirmed server value until
            # readback succeeds, including a busy/error response to a click.
            self._render_continuous()

    def _resume_round_queries(self):
        if self.closed or self._polling_suspended:
            return
        if self.stopping:
            self._exit_query_resume_pending = True
            return
        self._exit_query_resume_pending = False
        require_current_identity(self.identity)
        # An end request is not terminal state. Keep reconciling an active
        # round after HTTP failure or a still-active success response.
        self.round.start_polling(resume=True)

    def _exit_failed(self, error):
        if self.closed:
            return
        self._error(error)
        try:
            self._resume_round_queries()
        except Exception as identity_error:
            self._fatal(identity_error)

    def _exit_result(self, result=None):
        if self.closed:
            return
        self._trace("session.exit.response",
                    operation="exit",
                    contains_pk_info=isinstance(result,
                                                dict) and "pk_basic" in result)
        try:
            require_current_identity(self.identity)
            if isinstance(result, dict) and "pk_basic" in result:
                event = PkInfoEvent("PK_INFO", {}, parse_pk_info(result))
                if self.stopping:
                    self._pending_round_events.append(event)
                else:
                    self.round.handle_event(event)
            elif self.round_state.round_id and not self.stopping:
                self.round.query_current(self.round_state.round_id,
                                         replace=True)
            else:
                self._status("退出请求已提交，等待服务端状态更新")
            self._resume_round_queries()
        except Exception as error:
            self._exit_failed(error)

    def stop_round(self):
        self._trace("session.stop_round.requested")
        if self.closed:
            return
        if (self.options.mode == PkMode.TRADITIONAL
                and self.flow.phase not in (PkPhase.PREPARING,
                                            PkPhase.MATCHING)):
            # Classic has no verified manual end entry for an active round.
            # Cancelling an in-flight match is the one allowed exception.
            self._trace("session.stop_round.ignored",
                        reason="classic_manual_end_disabled")
            return
        if self.options.mode == PkMode.VIDEO_LINK and self.join_event is not None:
            self.disconnect()
            return
        if self.options.mode == PkMode.VIDEO_LINK and self.invitation_only:
            self.close()
            return
        if self.options.mode == PkMode.VIDEO_LINK and self.flow.phase == PkPhase.CONNECTING:
            self.flow.cancel()
            return
        if self.flow.phase == PkPhase.STOPPING or self.exit.busy:
            self._trace("session.stop_round.ignored",
                        reason="exit_or_cancel_pending")
            return
        if not self._business_started:
            self.close()
        elif self.flow.phase in (PkPhase.PREPARING, PkPhase.MATCHING,
                                 PkPhase.INVITING):
            self._polling_suspended = True
            self.round.stop_polling()
            self.flow.cancel()
        else:
            self.round.stop_polling()
            self.exit.exit_pk(end_round=True)

    def disconnect(self):
        self._trace("session.disconnect.requested")
        if self.closed:
            return
        if self.options.mode == PkMode.TRADITIONAL:
            self._trace("session.disconnect.ignored",
                        reason="classic_manual_end_disabled")
            return
        if self.join_event and not self.stopping:
            if self.options.mode == PkMode.VIDEO_LINK:
                from startlive.core.workers.pk.video_link import \
                    PkDisconnectLinkWorker
                from startlive.core.workers.base.CallbackPresenter import CallbackPresenter
                worker = PkDisconnectLinkWorker(
                    CallbackPresenter(finished=lambda _=None: None, failed=self._error),
                    self.identity, self.join_event.biz_session_id,
                    exit_pk=self.round_state.round_id > 0)
                try:
                    self.manager.submit(worker)
                finally:
                    self.close()
                return
            self.round.stop_polling()
            self.exit.disconnect_business_two(self.rtc.event.biz_session_id,
                                              trace_id=self.trace_id)

    def _rtc_finished(self):
        self._rtc_leave_deadline = None
        pending, self._pending_round_events = self._pending_round_events, []
        try:
            for event in pending:
                if self.closed:
                    break
                self.round.handle_event(event)
        except Exception as error:
            self._fatal(error)
        finally:
            # Keep the stopping gate through replay so terminal callbacks
            # cannot request the continuous switch a second time below.
            self.stopping = False
        self.presentation.render()
        if self._exit_query_resume_pending:
            try:
                self._resume_round_queries()
            except Exception as error:
                self._fatal(error)
        if self.invitations is not None:
            self.invitations.resume_waiting()
        self._refresh_continuous()
        if self.closed and not self.busy:
            self.view.set_active(False)

    def tick(self):
        """Called by the view's existing timer; never read a worker's event loop."""
        if not self.closed:
            try:
                require_current_identity(self.identity)
                if self.invitations is not None:
                    self.invitations.tick()
                if self.presentation.remaining_seconds() != self.presentation.remaining:
                    self.presentation.render()
                if not self.stopping:
                    self._check_rtc_leave_fallback()
                if not self.stopping:
                    self.round.tick()
            except Exception as error:
                self._fatal(error)
        if self.closed:
            if not self.busy:
                self.view.set_active(False)
            return
        if self._continuous_refresh_pending and self.continuous and not self.continuous.busy:
            self._continuous_refresh_pending = False
            self._refresh_continuous()
        if self.rtc is not None and self.rtc.worker and not self.stopping:
            facts = self.view._output_readiness(self.options.mode)
            if facts.output_ready is not True or facts.live_output_active is not True:
                self._status(facts.reason)
                self.close()
            elif self.rtc.room is not None:
                self.rtc.room.tick()

    def close(self):
        if self.closed:
            return
        self._trace("session.close.requested", pending_jobs=self.manager.busy)
        self._stop_rtc()
        if self.options.mode == PkMode.TRADITIONAL:
            self.view.stop_classic_audio()
        self.round_state.quit_round()
        self.closed = True
        if self.handle is not None:
            self.handle.retire()
        self.exit.retire()
        if self.continuous is not None:
            self.continuous.close()
        if self.view.provider_readiness is not None:
            self.view.provider_readiness.cancel(self)
        self._exit_query_resume_pending = False
        self.presentation.clock_key = self.presentation.deadline = self.presentation.remaining = None
        self.view.set_round_info(None)
        if self.invitations is not None:
            self.invitations.dismiss()
            self.invitations.accepted = None
        if self.invitation_only:
            self.view.set_invitation_waiting(False)
            self.view.dismiss_invitation()
        self._pending_round_events.clear()
        self.manager.retired = True
        self.push.stop()
        self.round.close()
        # Retire in-flight precheck/match callbacks and queued sends; an owner
        # that no longer belongs to the UI/account must not start requests.
        self.flow.retire()
        if not self.busy:
            self.view.set_active(False)

    @property
    def busy(self):
        # A completed Future still belongs to this session until the RTC
        # presenter's terminal callback has retired its GUI state.
        return self.manager.busy or (self.rtc is not None and self.rtc.worker is not None)

    @property
    def idle_invitation_listener(self):
        return self.invitations is not None and self.invitations.idle

    @property
    def join_event(self):
        return self.rtc.event if self.rtc is not None else None

    def set_invitation_reception(self, enabled):
        if self.invitations is not None:
            self.invitations.set_reception(enabled)

    def answer_invitation(self, event, accept):
        if self.invitations is not None:
            self.invitations.answer(event, accept)

    def set_publisher_muted(self, media, muted):
        if self.rtc is not None:
            self.rtc.set_muted(media, muted)

    def set_remote_muted(self, media, muted):
        if self.rtc is not None and self.rtc.business_mute is not None:
            self.rtc.business_mute.set_remote(media, muted)

    def start_connection_pk(self):
        if self.options.mode == PkMode.VIDEO_LINK:
            self.flow.start_pk()
