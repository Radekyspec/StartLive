"""One immutable account/flow owner, driven entirely on the GUI dispatcher.

Production availability is controlled by the view. Tests inject synthetic
HTTP/push/RTC transports without replacing the business controllers.
"""
from time import monotonic

from startlive.core.constant.pk import NativeInteractionState, NativePkType, \
    PkMode, PkPhase
from startlive.core.constant.pk_api import PK_CLASSIC_INFO_UNAVAILABLE
from startlive.core.constant.pk_info import NativePkState, PkInfoAction
from startlive.core.exceptions import PkError
from startlive.core.pk.identity import require_current_identity
from startlive.core.pk.pk_eligibility import pk_start_eligibility
from startlive.core.pk.pk_info import parse_pk_info
from startlive.core.pk.round_state import PkRoundState
from startlive.core.pk.states.eligibility import PkStartEligibilityState, \
    PkVideoEligibilityState
from startlive.core.pk.states.events import (
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
    PkJoinEligibility,
)
from startlive.core.pk.states.info import PkClassicInfoResult, PkInfoDecision
from startlive.core.pk.trace import pk_trace
from startlive.core.pk.trace_id import new_trace_id
from startlive.core.pk.video_eligibility import video_eligibility
from startlive.core.workers.pk.session_jobs import PkSessionJobs
from .continuous_controller import PkContinuousController
from .directed_invite import PkDirectedInviteController
from .exit_controller import PkExitController
from .match_controller import PkMatchController
from .push_controller import PkPushController
from .round_controller import PkRoundController
from .round_presentation import PkRoundPresentation


def _connection(ticket):
    from startlive.core.pk.rtc_connection import RtcConnection
    return RtcConnection(ticket)


class PkSessionController:
    def __init__(self, manager, identity, options, view, *, readiness,
                 identity_guard=require_current_identity,
                 connector_factory=_connection,
                 push_factory=PkPushController, rtc_factory=None,
                 invitation_display_allowed=False,
                 invitation_only=False, clock=monotonic,
                 provider_preflight=None, provider_readiness=None):
        manager = PkSessionJobs(manager)
        self.manager, self.identity, self.options, self.view = manager, identity, options, view
        self.readiness, self.identity_guard = readiness, identity_guard
        self._clock = clock
        self._owns_provider_readiness = provider_readiness is None
        self.provider_readiness = None
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
        self._pending_round_events = []
        self.invitations = self.rtc = self.join = self.handle = None
        self._rtc_initialization = (connector_factory, rtc_factory,
                                    provider_readiness, provider_preflight)
        if options.mode != PkMode.TRADITIONAL:
            self._initialize_video(*self._rtc_initialization)
        self.presentation = PkRoundPresentation(self)
        self.round_state = PkRoundState(self.kind,
                                        start_state_provider=self._start_facts)
        self.round = PkRoundController(manager, identity, self.round_state,
                                       changed=self._round_changed,
                                       cleanup_round=self._round_finished,
                                       refresh_continuous=self._refresh_continuous,
                                       terminal_notice=lambda _: self._status(
                                           "本轮 PK 已结束"),
                                       failed=self._error,
                                       identity_guard=identity_guard,
                                       clock=clock,
                                       trace_id=self.trace_id,
                                       polling_allowed=lambda: not (
                                               self.closed or self.stopping or self._polling_suspended))
        self.exit = PkExitController(manager, identity,
                                     reconcile=self._exit_result,
                                     failed=self._exit_failed,
                                     local_shutdown=self._stop_rtc,
                                     finished=lambda: None,
                                     pk_state_provider=lambda: self.round_state.state,
                                     round_id_provider=lambda: self.round_state.round_id)
        self.flow = (
            PkDirectedInviteController(manager, identity,
                                       sent=self._waiting,
                                       failed=self._flow_failed,
                                       intercepted=self._intercepted,
                                       cancelled=self._cancelled)
            if self.kind == NativePkType.DOUBLE_INVITE else
            PkMatchController(manager, identity, self.kind,
                              waiting=self._waiting,
                              cancelled=self._cancelled,
                              failed=self._flow_failed,
                              intercepted=self._intercepted))
        if options.mode == PkMode.VIDEO_LINK:
            from .video_link_controller import PkVideoLinkController
            self.flow = PkVideoLinkController(self)
        continuous_kind = NativePkType.DOUBLE_CLASSIC if options.mode == PkMode.TRADITIONAL else NativePkType.DOUBLE_RANDOM
        self.continuous = None if invitation_only or options.mode == PkMode.VIDEO_LINK else PkContinuousController(
            manager, identity, continuous_kind, changed=self._continuous_loaded,
            failed=self._continuous_failed, trace_id=self.trace_id,
            requeue_checked=self._continuous_requeue)
        self.push = push_factory(manager, identity, ready=self._push_ready,
                                 event=self.receive,
                                 failed=self._fatal)
        self._trace("session.created", mode=options.mode,
                    invitation_only=invitation_only,
                    requested_peer_uid=options.peer_search,
                    continuous=options.continuous)

    def _initialize_video(self, connector_factory, rtc_factory,
                          provider_readiness, provider_preflight):
        from .invitation_lifecycle import PkInvitationLifecycle
        from .rtc_lifecycle import PkRtcLifecycle
        from .handle_controller import PkHandleController
        from .join_controller import PkJoinController
        from .provider_readiness import VideoProviderReadiness

        if rtc_factory is None:
            from startlive.core.workers.pk.rtc_media import RtcMediaWorker
            rtc_factory = RtcMediaWorker
        if self.options.mode != PkMode.TRADITIONAL:
            self.provider_readiness = provider_readiness or VideoProviderReadiness(
                self.manager, provider_preflight)
            self.invitations = PkInvitationLifecycle(self)
        self.rtc = PkRtcLifecycle(self, connector_factory, rtc_factory)
        self.join = PkJoinController(self.identity, connect=self.rtc.connect,
                                     identity_guard=self.identity_guard,
                                     eligibility_check=self._join_eligibility)
        if self.invitations is not None:
            self.handle = PkHandleController(self.manager, self.identity,
                                             self.join,
                                             handled=self.invitations.handled,
                                             failed=self.invitations.failed,
                                             video_link=self.options.mode == PkMode.VIDEO_LINK)

    def _join_eligibility(self, event):
        if self.options.mode == PkMode.TRADITIONAL:
            facts = self.readiness(PkMode.TRADITIONAL)
            return PkJoinEligibility(
                event.biz_label == "classic_pk" and facts.output_ready is True
                and facts.live_output_active is True,
                "当前不能加入经典 PK 语音")
        if event.biz_label == "classic_pk":
            return PkJoinEligibility(False, "经典语音通知与当前模式不符")
        return video_eligibility(self._video_facts())

    def _stop_rtc(self):
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
                            "interaction_state": self.join.native_state if self.join else None,
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
            self.identity_guard(self.identity)
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
        facts = self.readiness(self.options.mode)
        return PkStartEligibilityState(facts.output_ready,
                                       facts.live_output_active,
                                       facts.voice_microphone_available,
                                       self.round_state.state)

    def _video_facts(self):
        facts = self.readiness(PkMode.VIDEO)
        return PkVideoEligibilityState(facts.output_ready,
                                       facts.live_output_active,
                                       self.join.native_state,
                                       2 if self.rtc.event else 0,
                                       self.round_state.state,
                                       self.round_state.kind)

    def start(self):
        self._trace("session.start.requested", mode=self.options.mode,
                    invitation_only=self.invitation_only)
        if self.started or self.closed:
            raise PkError("此 PK 会话已启动或关闭")
        self.identity_guard(self.identity)
        if self.invitation_only and (
                self.options.mode == PkMode.TRADITIONAL or self.options.peer_search is not None
                or self.options.continuous):
            raise PkError("等待邀请仅用于未指定对手的视频 PK")
        if self.options.mode == PkMode.TRADITIONAL and self.options.peer_search is not None:
            raise PkError("经典 PK 仅支持随机匹配")
        if self.kind == NativePkType.DOUBLE_INVITE and not self.invitation_only:
            if self.options.candidate is None or self.options.candidate.uid != self.options.peer_search:
                raise PkError("请搜索并选择视频 PK 对手")
        eligibility = (
            video_eligibility(self._video_facts()) if self.invitation_only else
            pk_start_eligibility(self.kind, self._start_facts()))
        if eligibility.allowed is not True:
            raise PkError(eligibility.reason)
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
                self.identity_guard(self.identity)
                ready()

        self.provider_readiness.ensure(self, completed,
                                       lambda error: failed(
                                           error) if not self.closed else None)

    def _start_push(self):
        if self.closed:
            return
        self.identity_guard(self.identity)
        eligibility = (
            video_eligibility(self._video_facts()) if self.invitation_only else
            pk_start_eligibility(self.kind, self._start_facts()))
        if eligibility.allowed is not True:
            raise PkError(eligibility.reason)
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
            self.identity_guard(self.identity)
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
        self.identity_guard(self.identity)
        decision = pk_start_eligibility(self.kind, self._start_facts())
        if decision.allowed is not True:
            self._fatal(PkError(decision.reason))
            return
        self.exit.retire()
        self._business_started = True
        self._trace("session.business.start",
                    requested_peer_uid=self.expected_peer_uid)
        if self.options.mode == PkMode.VIDEO_LINK:
            self.flow.invite(self.options.candidate, trace_id=self.trace_id)
            return
        self.round_state.state = NativePkState.STARTING
        self.presentation.info = self.presentation.peer_uid = None
        self.presentation.ended = False
        self.presentation.render()
        if self.kind == NativePkType.DOUBLE_INVITE:
            self.flow.invite(self.options.candidate, trace_id=self.trace_id)
        else:
            self.flow.start(trace_id=self.trace_id)

    def _waiting(self, _):
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

    def _intercepted(self, result):
        self._trace("session.precheck.intercepted", title=result.title,
                    content=result.content)
        self._status(result.content or result.title or "当前无法开始 PK")
        self.close()

    def _cancelled(self):
        self._trace("session.business.cancelled")
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
            self.identity_guard(self.identity)
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
                    if event.biz_label != "classic_pk" or self._join_eligibility(
                            event).allowed is not True:
                        return
                    self._initialize_video(*self._rtc_initialization)
                if self.options.mode == PkMode.VIDEO_LINK:
                    self.flow.join(event)
                    return
                if self.invitation_only and self.invitations.accepted is None:
                    self._trace("session.push.ignored", command=event.command,
                                reason="invitation_not_accepted")
                    return
                if not self.join.handle(event):
                    self._trace("session.push.ignored", command=event.command,
                                reason="duplicate_or_unusable_join")
            elif isinstance(event, PkLeaveEvent) and self.join_event:
                if (self.options.mode in (PkMode.TRADITIONAL, PkMode.VIDEO_LINK)
                        and event.biz_session_id
                        and event.biz_session_id != self.join_event.biz_session_id):
                    return
                decision = self.exit.server_leave(event,
                                                  rtc_channel_id=self.rtc.event.rtc_channel_id,
                                                  native_state=self.join.native_state)
                self._trace("session.leave.decision",
                            accepted=decision is not None,
                            event_rtc_channel_id=event.rtc_channel_id)
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
                    if self.round_state.round_id in (0, event.pk_id):
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
            self.presentation.info = result.info if isinstance(result,
                                                               PkInfoDecision) else None
            self.presentation.ended = (isinstance(result, PkInfoDecision)
                                       and result.action == PkInfoAction.ROUND_ENDED)
            self.presentation.render()
            if (isinstance(result,
                           PkClassicInfoResult) and result.code == PK_CLASSIC_INFO_UNAVAILABLE
                    and result.auto_match_status != 2 and isinstance(self.flow,
                                                                     PkMatchController)):
                self.flow.match_timed_out()
            self.view.set_active(False)
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
                self.join.native_state == NativeInteractionState.READY
                and self.rtc.future is None)

    def _continuous_requeue(self, status):
        if (
                self.closed or self.options.mode != PkMode.VIDEO or status.status != 2
                or status.effect_pk_version != 2 or not self._both_idle()):
            return
        self.identity_guard(self.identity)
        decision = pk_start_eligibility(NativePkType.DOUBLE_RANDOM,
                                        self._start_facts(),
                                        continuous_video=True)
        if decision.allowed is not True:
            self._status(decision.reason)
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
        self.identity_guard(self.identity)
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
        self.identity_guard(self.identity)
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

    def _exit_result(self, result):
        if self.closed:
            return
        self._trace("session.exit.response",
                    operation=getattr(result, "operation", None),
                    contains_pk_info=isinstance(result.data,
                                                dict) and "pk_basic" in result.data)
        try:
            self.identity_guard(self.identity)
            if isinstance(result.data, dict) and "pk_basic" in result.data:
                event = PkInfoEvent("PK_INFO", {}, parse_pk_info(result.data))
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
        if self.join_event and not self.closed and not self.stopping:
            if self.options.mode == PkMode.VIDEO_LINK:
                from startlive.core.workers.pk.video_link import \
                    PkDisconnectLinkWorker
                from .pk_presenter import PkPresenter
                worker = PkDisconnectLinkWorker(
                    PkPresenter(finished=lambda _: None, failed=self._error),
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

    def tick(self):
        """Called by the view's existing timer; never read a worker's event loop."""
        if not self.closed:
            try:
                self.identity_guard(self.identity)
                if self.invitations is not None:
                    self.invitations.tick()
                if self.presentation.remaining_seconds() != self.presentation.remaining:
                    self.presentation.render()
                if not self.stopping:
                    self.round.tick()
            except Exception as error:
                self._fatal(error)
        if self.rtc is not None and self.rtc.finish_if_done():
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
            if self.closed and not self.manager.busy:
                self.view.set_active(False)
        if self.closed:
            if not self.manager.busy:
                self.view.set_active(False)
            return
        if self._continuous_refresh_pending and self.continuous and not self.continuous.busy:
            self._continuous_refresh_pending = False
            self._refresh_continuous()
        if self.rtc is not None and self.rtc.worker and not self.stopping:
            facts = self.readiness(self.options.mode)
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
        self.closed = True
        if self.handle is not None:
            self.handle.retire()
        self.exit.retire()
        if self.provider_readiness is not None:
            self.provider_readiness.cancel(self)
            if self._owns_provider_readiness:
                self.provider_readiness.close()
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
        # Retire in-flight precheck/match callbacks; do not start new requests
        # from an owner that no longer belongs to the UI/account.
        if not isinstance(self.flow, PkMatchController):
            self.flow.retire()
        else:
            self.flow.phase = PkPhase.FINISHED
        if not self.manager.busy:
            self.view.set_active(False)

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
