from time import monotonic

from startlive.core.constant.pk import NativePkType
from startlive.core.constant.pk_api import PK_CLASSIC_INFO_UNAVAILABLE
from startlive.core.constant.pk_info import NativePkState, PkInfoAction
from startlive.core.exceptions import PkError
from startlive.core.pk.identity import require_current_identity
from startlive.core.pk.pk_info import classic_pk_info, queried_pk_info
from startlive.core.pk.states.events import PkInfoEvent, PkMatchTimeoutEvent
from startlive.core.pk.states.info import PkClassicInfoResult
from startlive.core.pk.trace import pk_trace
from startlive.core.workers.pk.fetch_classic_info import PkClassicInfoWorker
from startlive.core.workers.pk.fetch_info import PkInfoWorker
from .pk_presenter import PkPresenter


class PkRoundController:
    """One account/flow owner for PK_INFO and classic query reconciliation.

    cleanup_round must release only round state/UI. No RTC shutdown dependency
    is accepted here: neither state Exit nor a terminal PK status proves Leave.
    Callbacks run on the GUI dispatcher through the injected worker presenter.
    """

    def __init__(self, manager, identity, state, *, changed, cleanup_round,
                 refresh_continuous, terminal_notice, failed,
                 identity_guard=require_current_identity,
                 clock=monotonic, polling_allowed=lambda: True, trace_id=""):
        self.manager, self.identity, self.state = manager, identity, state
        self.changed, self.cleanup_round = changed, cleanup_round
        self.refresh_continuous, self.terminal_notice = refresh_continuous, terminal_notice
        self.failed, self.identity_guard = failed, identity_guard
        self._query_serial, self._pending_id, self._closed = 0, None, False
        self._repeat_id = None
        self._pending_classic = None
        self._pending_serial = None
        self._clock, self._poll_deadline = clock, None
        self._polling_allowed = polling_allowed
        self.trace_id = trace_id

    def _trace(self, event, **fields):
        pk_trace(event, **({"trace_id": self.trace_id, "uid": self.identity.uid,
                            "room_id": self.identity.room_id,
                            "pk_id": self.state.round_id,
                            "biz_session_id": self.state.biz_session_id,
                            "pk_state": self.state.state,
                            "kind": self.state.kind,
                            "current_timestamp": self.state.timestamp} | fields))

    @property
    def polling(self):
        return self._poll_deadline is not None

    def start_polling(self, *, resume=False):
        """Arm matching, or resume an unresolved round after a local exit request."""
        eligible_state = (self.state.state == NativePkState.MATCHING or
                          resume and NativePkState.SELECTING_USER <= self.state.state < NativePkState.END)
        if (self._closed or not self._polling_allowed() or not eligible_state
                or self.state.kind not in (NativePkType.DOUBLE_CLASSIC,
                                           NativePkType.DOUBLE_RANDOM,
                                           NativePkType.DOUBLE_INVITE)):
            return False
        if self._poll_deadline is None:
            self._poll_deadline = self._clock() + 1
            self._trace("round.polling.started", resume=resume)
        return True

    def stop_polling(self):
        """Stop scheduled work and retire replies, preserving in-flight ownership."""
        if self._poll_deadline is not None or self._pending_id is not None:
            self._trace("round.polling.stopped", pending_pk_id=self._pending_id)
        self._poll_deadline = None
        self._query_serial += 1
        self._repeat_id = None
        # Keep the pending worker marker until its callback arrives. A later
        # explicit current-state query can wait for it without overlapping.

    def tick(self):
        if self._closed or self._poll_deadline is None:
            return False
        try:
            if not self._polling_allowed():
                self.stop_polling()
                return False
            self.identity_guard(self.identity)
            now = self._clock()
            if now < self._poll_deadline:
                return False
            self._poll_deadline = now + 1
            if self._pending_id is not None:
                # A slow response must still be consumed; periodic ticks do
                # not replace it or build a queue of redundant refreshes.
                return False
            return self.query_current(self.state.round_id)
        except Exception as error:
            self.stop_polling()
            self.failed(error)
            return False

    def handle_event(self, event):
        if self._closed or not isinstance(event, PkInfoEvent):
            return False
        try:
            self.identity_guard(self.identity)
            previous_timestamp = self.state.timestamp
            return self._dispatch(self.state.from_push(event.info),
                                  previous_timestamp=previous_timestamp)
        except Exception as error:
            self._trace("round.push.failed", response=event.raw,
                        error_type=type(error).__name__, error=str(error))
            self.failed(error)
            return False

    def handle_match_timeout(self, event):
        """Contract43: retire only a matching attempt in a supported family.

        There is no attempt ID to compare. The authenticated account owner
        remains the caller's scope; a timeout is not RTC Leave or round END.
        """
        if self._closed or not isinstance(event, PkMatchTimeoutEvent):
            return False
        try:
            self.identity_guard(self.identity)
            expected = {NativePkType.DOUBLE_CLASSIC: 1,
                        NativePkType.DOUBLE_RANDOM: 2}.get(self.state.kind)
            if self.state.state != NativePkState.MATCHING or expected is None or event.battle_type != expected:
                self._trace("round.match_timeout.ignored",
                            battle_type=event.battle_type,
                            expected_battle_type=expected,
                            reason="not_current_matching_family")
                return False
            self._match_timed_out(event)
            return True
        except Exception as error:
            self._trace("round.push.failed", response=event.raw,
                        error_type=type(error).__name__, error=str(error))
            self.failed(error)
            return False

    def _match_timed_out(self, context):
        # Stop pending/repeated queries; an already-issued HTTP response
        # must not revive this matching attempt after it times out.
        self._trace("round.match_timeout.accepted",
                    context_type=type(context).__name__)
        self.stop_polling()
        self.state.state = NativePkState.IDLE
        self.cleanup_round(context)
        self.failed(PkError("PK 匹配超时，可尝试重新匹配"))

    def query_classic(self, pk_id, *, replace=False):
        if self._closed:
            return False
        if self.state.kind != NativePkType.DOUBLE_CLASSIC:
            raise PkError("此模式尚未接入状态查询")
        if type(pk_id) is not int or pk_id <= 0:
            raise PkError("经典 PK 回合查询需要有效的回合 ID")
        return self._query(pk_id, classic=True, replace=replace)

    def query_classic_current(self, *, replace=False):
        """Contract44 post-terminal owner refresh; not the completed round."""
        if self._closed:
            return False
        if self.state.kind != NativePkType.DOUBLE_CLASSIC:
            raise PkError("此模式尚未接入经典 PK 当前状态查询")
        return self._query(0, classic=True, replace=replace)

    def query_current(self, pk_id, *, replace=False):
        if self.state.kind == NativePkType.CHATROOM_GROUP and pk_id == 0:
            raise PkError("此语音 PK 模式的初始查询尚未接入")
        if self.state.kind == NativePkType.DOUBLE_CLASSIC:
            return (self.query_classic_current(replace=replace) if pk_id == 0
                    else self.query_classic(pk_id, replace=replace))
        return self._query(pk_id, classic=False, replace=replace)

    def _query(self, pk_id, *, classic, replace=False):
        if self._closed:
            return False
        self.identity_guard(self.identity)
        if self._pending_id is not None:
            if replace or (self._pending_id, self._pending_classic) != (pk_id,
                                                                        classic):
                # WorkerManager permits only one worker of each class. Keep
                # the latest requested refresh, discarding the earlier reply.
                self._repeat_id = (pk_id, classic)
                return True
            return False
        self._query_serial += 1
        serial = self._query_serial
        self._pending_serial = serial
        self._pending_id = pk_id
        self._pending_classic = classic
        self._trace("round.query.started", requested_pk_id=pk_id,
                    classic=classic)
        try:
            worker_class = PkClassicInfoWorker if classic else PkInfoWorker
            worker = worker_class(PkPresenter(
                finished=lambda result: self._queried(serial, pk_id, result,
                                                      classic=classic),
                failed=lambda error: self._query_failed(serial, error,
                                                        pk_id=pk_id,
                                                        classic=classic)),
                self.identity, pk_id,
                **({"current_state": pk_id == 0} if classic else {}))
            worker.request_allowed = lambda: not self._closed and serial == self._query_serial and self._polling_allowed()
            self.manager.submit(worker)
        except Exception as error:
            self._query_failed(serial, error, pk_id=pk_id, classic=classic)
        return True

    def _query_failed(self, serial, error, *, pk_id, classic):
        if self._take_reply(serial):
            self._trace("round.query.failed",
                        **self._query_context(pk_id, classic),
                        error_type=type(error).__name__, error=str(error))
            self.failed(error)

    def _query_context(self, pk_id, classic):
        request = {"pk_id": str(pk_id), "room_id": str(self.identity.room_id)}
        if classic:
            request["is_anchor"] = "1"
        return {"operation": "classic_info" if classic else "info",
                "request": request}

    def _take_reply(self, serial):
        if self._closed or serial != self._pending_serial:
            self._trace("round.query.reply_ignored",
                        reason="closed_or_not_pending_serial")
            return False
        current = serial == self._query_serial
        self._pending_id = None
        self._pending_classic = None
        self._pending_serial = None
        if self._repeat_id is not None:
            request, self._repeat_id = self._repeat_id, None
            self._effect(lambda: self._query(request[0], classic=request[1]))
            self._trace("round.query.reply_ignored",
                        reason="replacement_requested")
            return False
        if not current:
            self._trace("round.query.reply_ignored", reason="retired_query")
        return current

    def _queried(self, serial, pk_id, result, *, classic):
        if not self._take_reply(serial):
            return
        try:
            self.identity_guard(self.identity)
            if classic:
                response = result.data
                if not isinstance(response, PkClassicInfoResult):
                    raise PkError("经典 PK 查询响应无效")
                if response.code == PK_CLASSIC_INFO_UNAVAILABLE:
                    self._trace("round.classic.recovery", code=response.code,
                                auto_match_status=response.auto_match_status)
                    # Contract44 applies only while this owner remains kind9.
                    if self.state.kind != NativePkType.DOUBLE_CLASSIC:
                        return
                    if response.auto_match_status == 2:
                        if self.state.state == NativePkState.MATCHING:
                            return
                    else:
                        if self.state.state == NativePkState.MATCHING:
                            self._match_timed_out(response)
                        else:
                            self.stop_polling()
                            self.state.quit_round()
                            self.cleanup_round(response)
                        return
                info = classic_pk_info(response.data,
                                       auto_matching=response.code == PK_CLASSIC_INFO_UNAVAILABLE,
                                       cached_timestamp=self.state.timestamp)
            else:
                info = queried_pk_info(result.data)
            if not classic and self.state.state == NativePkState.IDLE and info.basic.pk_id == self.state.last_ended_round_id:
                self._trace("round.query.reply_ignored",
                            event_pk_id=info.basic.pk_id,
                            reason="already_ended_round")
                return
            if pk_id and info.basic.pk_id not in (0, pk_id):
                raise PkError("PK 查询返回了其他回合的信息")
            previous_timestamp = self.state.timestamp
            self._dispatch(self.state.apply(info),
                           previous_timestamp=previous_timestamp)
        except Exception as error:
            self._trace("round.query.failed",
                        **self._query_context(pk_id, classic),
                        response=result, stage="callback",
                        error_type=type(error).__name__, error=str(error))
            self.failed(error)

    def _dispatch(self, decision, *, previous_timestamp=None):
        action = decision.action
        self._trace("round.decision", action=action, reason=decision.reason,
                    previous_state=decision.previous_state,
                    state=decision.state,
                    previous_timestamp=previous_timestamp,
                    incoming_timestamp=decision.info.timestamp,
                    incoming_status=decision.info.basic.status,
                    event_pk_id=decision.info.basic.pk_id,
                    event_biz_session_id=decision.info.basic.biz_session_id,
                    source_kind=decision.info.source_kind)
        if action == PkInfoAction.IGNORED:
            return False
        if action == PkInfoAction.BLOCKED:
            raise PkError(decision.reason)
        if action == PkInfoAction.QUERY:
            return self.query_current(decision.info.basic.pk_id)
        if action == PkInfoAction.ROUND_ENDED:
            # Contract21 confirmed invocation order, with no HTTP completion
            # barrier and no automatic new match or RTC disconnection.
            self.stop_polling()
            self._effect(lambda: self.cleanup_round(decision))
            self._effect(self.refresh_continuous)
            if self.state.kind == NativePkType.DOUBLE_CLASSIC:
                self._effect(lambda: self.query_classic_current(replace=True))
            self._effect(lambda: self.terminal_notice(decision))
        elif action == PkInfoAction.ROUND_IDLE:
            self.stop_polling()
            self.cleanup_round(decision)
        else:
            if decision.state == NativePkState.MATCHING:
                self.start_polling()
            self.changed(decision)
        return True

    def _effect(self, callback):
        try:
            callback()
        except Exception as error:
            # E.g. a continuous-switch refresh already in progress must not
            # prevent classic reconciliation or the terminal notification.
            self.failed(error)

    def close(self):
        """Invalidate pending callbacks when this account/flow owner retires."""
        self.stop_polling()
        self._closed = True
        self._pending_id = self._pending_classic = self._pending_serial = None
