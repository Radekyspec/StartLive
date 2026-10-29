from startlive.core.exceptions import PkError
from startlive.core.pk.identity import current_identity
from startlive.core.pk.trace import pk_trace
from startlive.core.pk.user_settings import build_settings_change
from startlive.core.workers.pk.fetch_user_settings import \
    FetchPkUserSettingsWorker
from startlive.core.workers.pk.update_user_settings import \
    UpdatePkUserSettingsWorker
from startlive.PySide.interface_adapters.pk.settings_presenter import PkSettingsPresenter


class PkSettingsController:
    """Serialize full-snapshot edits and apply only the owning account's reply."""

    def __init__(self, window):
        self.window = window
        self.view = window._settings_dialog
        self.identity = self.snapshot = None
        self.busy = self.closed = False
        self._sequence = 0

    def refresh(self):
        if self.closed or self.busy:
            return
        try:
            identity = current_identity()
            if identity != self.identity:
                self._clear()
                self.identity = identity
            self._submit(FetchPkUserSettingsWorker(
                self._begin_request(), self.identity))
        except Exception as error:
            self._failed(error)

    def change(self, field, value):
        if self.closed or self.busy:
            return
        try:
            if self.snapshot is None:
                raise PkError("请先读取当前账号的 PK 设置")
            self._require_account()
            submitted = build_settings_change(self.snapshot, field, value)
            if submitted == self.snapshot:
                return
            self._trace("settings.change", field=field, value=value)
            self._submit(UpdatePkUserSettingsWorker(
                self._begin_request(saving=True), self.identity, submitted))
        except Exception as error:
            self._failed(error)

    def _begin_request(self, *, saving=False):
        self._sequence += 1
        self.busy = True
        self.view.set_error("")
        self.view.set_busy(True)
        return PkSettingsPresenter(self, self._sequence, saving=saving)

    def _request_current(self, sequence):
        return not self.closed and sequence == self._sequence and self.busy

    def _submit(self, worker):
        sequence = self._sequence
        worker.request_allowed = lambda: self._request_current(sequence)
        try:
            self.window._workers.submit(worker, on_progress=True)
        except Exception as error:
            worker.on_exception(error)

    def _require_account(self):
        try:
            matches = current_identity() == self.identity
        except Exception as error:
            self._clear()
            self.identity = None
            raise PkError(
                f"无法确认 PK 设置所属账号：{type(error).__name__}: {error}") from error
        if not matches:
            self._clear()
            self.identity = None
            raise PkError("登录账号已改变，请刷新 PK 设置")

    def _clear(self):
        self.snapshot = None
        self.view.clear_values()

    def _loaded(self, snapshot):
        self._show_snapshot(snapshot)
        self._finish_request()

    def _show_snapshot(self, snapshot):
        self.snapshot = snapshot
        self.view.set_values(snapshot.preferences,
                             tuple((value, f"{value}分钟") for value in
                                   snapshot.duration_options))
        self._trace("settings.confirmed", values=snapshot.preferences)
        self.window._settings_confirmed(snapshot)

    def _saved(self, message):
        self._finish_request()
        self._trace("settings.saved", message=message)

    def _finish_request(self):
        self.busy = False
        self.view.set_busy(False)

    def _failed(self, error):
        if self.closed:
            return
        self._finish_request()
        self.view.set_error(str(error) or type(error).__name__)
        self._trace("settings.failed", error_type=type(error).__name__, error=str(error))

    def _trace(self, event, **fields):
        pk_trace(event, uid=getattr(self.identity, "uid", None),
                 room_id=getattr(self.identity, "room_id", None), **fields)

    def close(self):
        self.closed = True
        self._sequence += 1
        self.busy = False
