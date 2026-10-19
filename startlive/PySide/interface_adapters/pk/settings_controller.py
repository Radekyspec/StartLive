from startlive.core.exceptions import PkError
from startlive.core.pk.identity import current_identity
from startlive.core.pk.trace import pk_trace
from startlive.core.pk.user_settings import build_settings_change
from startlive.core.workers.pk.fetch_user_settings import \
    FetchPkUserSettingsWorker
from startlive.core.workers.pk.update_user_settings import \
    UpdatePkUserSettingsWorker
from .pk_presenter import PkPresenter


class PkSettingsController:
    """Serialize full-snapshot edits and apply only the owning account's reply."""

    def __init__(self, manager, view, *, identity_provider=current_identity,
                 confirmed=None):
        self.manager, self.view = manager, view
        self.identity_provider, self.confirmed = identity_provider, confirmed
        self.identity = self.snapshot = None
        self.busy = self.closed = False
        self._sequence = 0

    def refresh(self):
        if self.closed or self.busy:
            return
        try:
            identity = self.identity_provider()
            if identity != self.identity:
                self._clear()
                self.identity = identity
            self._submit(FetchPkUserSettingsWorker, self._loaded)
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
            self._submit(lambda presenter, identity: UpdatePkUserSettingsWorker(
                presenter, identity, submitted), self._saved)
        except Exception as error:
            self._failed(error)

    def _submit(self, factory, completed):
        self._sequence += 1
        sequence = self._sequence
        self.busy = True
        self.view.set_error("")
        self.view.set_busy(True)
        worker = None
        try:
            worker = factory(PkPresenter(
                finished=lambda result: self._complete(sequence, completed,
                                                       result),
                failed=lambda error: self._complete(sequence, self._failed,
                                                    error)), self.identity)
            self.manager.submit(worker)
        except Exception as error:
            self._failed(error)

    def _complete(self, sequence, completed, result):
        if self.closed or sequence != self._sequence or not self.busy:
            return
        try:
            self._require_account()
            completed(result)
        except Exception as error:
            self._failed(error)

    def _require_account(self):
        try:
            matches = self.identity_provider() == self.identity
        except Exception:
            matches = False
        if not matches:
            self._clear()
            self.identity = None
            raise PkError("登录账号已改变，请刷新 PK 设置")

    def _clear(self):
        self.snapshot = None
        self.view.clear_values()

    def _loaded(self, snapshot):
        self.snapshot = snapshot
        self.busy = False
        self.view.set_values(snapshot.preferences,
                             tuple((value, f"{value}分钟") for value in
                                   snapshot.duration_options))
        self.view.set_busy(False)
        self._trace("settings.confirmed", values=snapshot.preferences)
        if self.confirmed is not None:
            self.confirmed(snapshot)

    def _saved(self, result):
        self._trace("settings.saved", message=result.message)
        expected = result.snapshot.preferences

        def verified(snapshot):
            self._loaded(snapshot)
            if snapshot.preferences != expected:
                raise PkError("PK 设置回读与提交不一致，已显示服务端当前设置")

        self._submit(FetchPkUserSettingsWorker, verified)

    def _failed(self, error):
        if self.closed:
            return
        self.busy = False
        self.view.set_busy(False)
        self.view.set_error(str(error))
        self._trace("settings.failed", error=str(error))

    def _trace(self, event, **fields):
        pk_trace(event, uid=getattr(self.identity, "uid", None),
                 room_id=getattr(self.identity, "room_id", None), **fields)

    def close(self):
        self.closed = True
        self._sequence += 1
        self.busy = False
