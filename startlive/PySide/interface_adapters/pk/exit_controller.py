from startlive.core.constant.pk_info import NativePkState
from startlive.core.exceptions import PkError
from startlive.core.pk.business_session import local_quit_from_business_leave
from startlive.core.workers.pk.exit_pk import PkExitWorker
from startlive.core.workers.pk.quit_connection import PkQuitConnectionWorker
from .request_attempt import RequestAttempt


class PkExitController:
    """PK exit and the verified business2 disconnect confirmation are separate.

    Local shutdown initiates worker cleanup only; this class does not invent
    RTC Leave/unpublish packets or treat PK_BATTLE_END as interaction leave.
    """

    def __init__(self, manager, identity, *, reconcile, failed, local_shutdown,
                 finished,
                 pk_state_provider, round_id_provider):
        self.manager, self.identity = manager, identity
        self.reconcile, self.failed = reconcile, failed
        self.local_shutdown, self.finished = local_shutdown, finished
        self._pk_state_provider = pk_state_provider
        self._round_id_provider = round_id_provider
        self._ended_round_id = None
        self._pending = set()
        self._issuing = False
        self._attempt = RequestAttempt()

    def retire(self):
        """Detach replies when the owner closes or starts a new business attempt."""
        self._attempt.invalidate()
        self._pending.clear()
        self._ended_round_id = None

    @property
    def busy(self):
        return bool(self._pending) or self._issuing

    def exit_pk(self, *, end_round):
        if self.busy:
            raise PkError("退出 PK 请求正在处理")
        if not self._has_active_pk():
            self.finished()
            return
        self._attempt.invalidate()
        self._pending = {"exit"}
        self._submit_exit(end_round)

    def server_leave(self, event, *, rtc_channel_id, native_state,
                     business_label=None):
        """Call only for this controller's captured account/flow event stream.

        Server LEAVE takes the guarded local path, independently of any HTTP
        requests already in flight. It never manufactures Exit/Quit requests.
        """
        decision = local_quit_from_business_leave(event,
                                                  rtc_channel_id=rtc_channel_id,
                                                  native_state=native_state,
                                                  business_label=business_label)
        if decision is not None:
            self.local_shutdown()
        return decision

    def disconnect_business_two(self, biz_session_id, *, trace_id):
        """main472560: guarded ReqExitPk -> Quit -> local shutdown."""
        if self.busy:
            raise PkError("退出 PK 请求正在处理")
        if not biz_session_id:
            raise PkError("断开视频连接需要当前会话信息")
        self._attempt.invalidate()
        exit_pk = self._has_active_pk()
        self._pending, self._issuing = (
            {"exit", "quit"} if exit_pk else {"quit"}), True
        try:
            if exit_pk:
                self._submit_exit(True)
            self._submit(PkQuitConnectionWorker(self._presenter("quit"),
                                                self.identity,
                                                biz_session_id,
                                                trace_id=trace_id))
        finally:
            # No HTTP completion barrier in this explicit native branch.
            try:
                self.local_shutdown()
            finally:
                self._issuing = False
                self._finish_if_done()

    def _has_active_pk(self):
        # mainbd9cd0 at bd9e32 skips ReqExitPk when controller+110 is 0.
        if self._pk_state_provider() == NativePkState.IDLE:
            return False
        # StartLive idempotency: a successful stop_pk=1 already ended this
        # round. A subsequent disconnect still sends Quit and stops RTC, but
        # must not issue the same Exit while terminal PK_INFO is in flight.
        round_id = self._current_round_id()
        return round_id is None or round_id != self._ended_round_id

    def _current_round_id(self):
        value = self._round_id_provider()
        return value if type(value) is int and value > 0 else None

    def _presenter(self, operation):
        return self._attempt.presenter(
            lambda result: self._done(operation, result),
            lambda error: self._done(operation, error=error))

    def _submit_exit(self, end_round):
        round_id = self._current_round_id()

        def succeeded(result):
            if end_round and round_id is not None:
                self._ended_round_id = round_id
            self._done("exit", result)

        presenter = self._attempt.presenter(succeeded,
                                            lambda error: self._done("exit",
                                                                     error=error))
        self._submit(PkExitWorker(presenter, self.identity,
                                  end_round=end_round))

    def _submit(self, worker):
        # Exit/Quit are generation-bound too: retire() must stop queued sends
        # after stopLive/owner shutdown, not only discard their callbacks.
        self._attempt.submit(self.manager, worker)

    def _done(self, operation, result=None, error=None):
        self._pending.discard(operation)
        if error is not None:
            self.failed(error)
        elif operation == "exit":
            self.reconcile(
                result)  # Returned PK info is preserved for the session.
        self._finish_if_done()

    def _finish_if_done(self):
        if not self.busy:
            self.finished()
