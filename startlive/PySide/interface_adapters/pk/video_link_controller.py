"""1v1 Connect flow; transport, invitation UI and RTC remain shared."""
from startlive.core.constant.pk import PkPhase
from startlive.core.constant.pk_info import NativePkState
from startlive.core.exceptions import PkError
from startlive.core.pk.pk_info import queried_pk_info
from startlive.core.pk.states.events import PkInvitationEvent
from startlive.core.workers.pk.video_link import (
    PkConnectWorker, PkCancelConnectWorker, PkConnectionStartWorker,
    PkInteractListWorker,
)
from .request_attempt import RequestAttempt


class PkVideoLinkController:
    def __init__(self, session):
        self.session = session
        self.phase = PkPhase.IDLE
        self.candidate = None
        self.biz_session_id = ""
        self.pending_joins = {}
        self.seen_invitations = set()
        self.pending_operations = []
        self.connecting_request = self.cancel_requested = self.starting_pk = False
        self.list_busy = self.list_again = False
        self.attempt = RequestAttempt()

    def invite(self, candidate):
        self.candidate = candidate
        self.phase = PkPhase.INVITING
        self.connecting_request = True
        self.attempt.invalidate()
        worker = PkConnectWorker(
            self.attempt.presenter(self._connected, self._failed),
            self.session.identity, candidate)
        worker.request_allowed = lambda: not self.session.closed
        self.attempt.submit(self.session.manager, worker)

    def _connected(self, result):
        self.connecting_request = False
        data = result.data
        value = data.get("biz_session_id") if isinstance(data, dict) else None
        if not isinstance(value, str) or not value:
            self._failed(PkError("Connect 响应缺少连线会话 ID"))
            return
        self.biz_session_id = value
        self.session.round_state.biz_session_id = value
        self.refresh_list()
        if self.cancel_requested:
            self._cancel()
            return
        self.session._status("等待对方接受视频连线邀请…")
        operations, self.pending_operations = self.pending_operations, []
        event = self.pending_joins.pop(value, None)
        self.pending_joins.clear()
        if event is not None and not self.session.closed:
            self.join(event)
        # An admitted JOIN wins over a delayed pending-invitation result,
        # including when both notifications preceded the Connect response.
        for event in operations:
            self.operation(event)

    def operation(self, event):
        session = self.session
        if session.closed or session.stopping:
            return
        if event.operation_type == 0:
            if (
                    event.biz_label != "universal_multi_conn" or event.uid != session.identity.uid
                    or not event.biz_session_id or not event.initiator or event.source not in (
                    4, 7)
                    or event.biz_session_id in self.seen_invitations):
                return
            # Incoming identity comes exclusively from this notification.
            invite = PkInvitationEvent(event.command, event.raw,
                                       event.biz_session_id,
                                       event.rtc_channel_id, event.uid, None,
                                       event.initiator,
                                       event.source, None,
                                       event.invitation_timeout, "",
                                       event.user_info)
            session.invitations.present(invite)
            if session.invitations.pending is invite:
                self.seen_invitations.add(event.biz_session_id)
            return
        if event.operation_type == 3 and session.invitation_only:
            invite = session.invitations.pending
            if (
                    invite is not None and event.biz_session_id == invite.biz_session_id
                    and event.source == invite.source
                    and event.operator_uid == invite.initiator):
                session.invitations.dismiss()
                session._status("对方已取消邀请，继续等待视频连线邀请…")
                self.refresh_list()
            return
        if session.invitation_only or self.phase not in (PkPhase.INVITING,
                                                         PkPhase.CONNECTING):
            return
        if event.target_uid != session.expected_peer_uid:
            return
        if self.connecting_request:
            if len(self.pending_operations) < 8:
                self.pending_operations.append(event)
            return
        if not self.biz_session_id or event.biz_session_id != self.biz_session_id:
            return
        if event.operation_type in (2, 4) and session.rtc.future is None:
            self.refresh_list()
            session._status(
                "对方已拒绝连线" if event.operation_type == 2 else "连线邀请已超时")
            session.close()
        elif event.operation_type == 1 and session.rtc.future is None:
            self.phase = PkPhase.CONNECTING
            session._status("对方已接受，等待入会通知…")

    def join(self, event):
        session = self.session
        if event.biz_label != "universal_multi_conn" or self.cancel_requested:
            return False
        if session.invitation_only:
            invite = session.invitations.accepted
            expected = invite.biz_session_id if invite is not None else None
        else:
            if self.connecting_request:
                if len(self.pending_joins) < 8 or event.biz_session_id in self.pending_joins:
                    self.pending_joins[event.biz_session_id] = event
                return False
            expected = self.biz_session_id
        if not expected or event.biz_session_id != expected:
            return False
        result = session.join.handle(event)
        if result:
            self.phase = PkPhase.ACTIVE
            self.refresh_list()
        return result

    def handoff(self):
        self.phase = PkPhase.ACTIVE

    def cancel(self):
        if self.phase == PkPhase.STOPPING:
            return
        self.cancel_requested = True
        self.phase = PkPhase.STOPPING
        if not self.connecting_request:
            self._cancel()

    def _cancel(self):
        worker = PkCancelConnectWorker(self.attempt.presenter(
            lambda _: self._cancelled(), self._failed), self.session.identity,
            self.candidate.uid)
        worker.request_allowed = lambda: not self.session.closed
        self.attempt.submit(self.session.manager, worker)

    def _cancelled(self):
        self.refresh_list()
        self.session._status("已取消视频连线邀请")
        self.session.close()

    def _failed(self, error):
        self.session._error(error)
        self.session.close()

    def refresh_list(self):
        if self.list_busy:
            self.list_again = True
            return
        self.list_busy = True

        def done(_):
            self.list_busy = False
            if self.list_again and not self.session.closed:
                self.list_again = False
                self.refresh_list()

        worker = PkInteractListWorker(self.attempt.presenter(done, done),
                                      self.session.identity)
        self.attempt.submit(self.session.manager, worker)

    def start_pk(self):
        session = self.session
        if (
                session.closed or session.stopping or not session.rtc.publisher_ready
                or session.join_event is None or self.starting_pk
                or session.round_state.state != NativePkState.IDLE):
            raise PkError("请在视频连线就绪且没有 PK 回合时转为 PK")
        self.starting_pk = True

        def loaded(result):
            self.starting_pk = False
            if session.closed or session.stopping:
                return
            try:
                info = queried_pk_info(result.data)
                if info.basic.pk_id <= 0 or info.basic.biz_session_id != session.join_event.biz_session_id:
                    raise PkError("转 PK 响应与当前连线不符")
                if info.basic.pk_id == session.round_state.last_ended_round_id:
                    return
                if session.round_state.state == NativePkState.IDLE:
                    session.round_state.state = NativePkState.PREPARING
                session.round._dispatch(session.round_state.apply(info))
                session.round.start_polling(resume=True)
            except Exception as error:
                session._error(error)

        def failed(error):
            self.starting_pk = False
            session._error(error)

        worker = PkConnectionStartWorker(self.attempt.presenter(loaded, failed),
                                         session.identity,
                                         session.join_event.biz_session_id)
        serial = self.attempt.serial
        worker.request_allowed = lambda: (
                    not session.closed and not session.stopping
                    and serial == self.attempt.serial)
        self.attempt.submit(session.manager, worker)

    def retire(self):
        self.attempt.invalidate()
        self.phase = PkPhase.FINISHED
        self.pending_joins.clear()
        self.pending_operations.clear()
        self.biz_session_id = ""
        self.connecting_request = self.cancel_requested = self.starting_pk = False
        self.list_busy = self.list_again = False
