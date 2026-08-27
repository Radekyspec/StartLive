import logging
import unittest
from contextlib import ExitStack
from json import loads
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from unittest.mock import patch

import keyring
from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QAction
from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QLabel,
    QLineEdit,
    QMainWindow,
    QStackedWidget,
    QWidget,
)

from src.PySide.classes import ClickableLabel
from src.PySide.interface_adapters import GUIDispatcher
from src.PySide.interface_adapters.credentials import (
    CredentialManagerPresenter,
)
from src.PySide.states import LoginState
from src.PySide.widgets import StartLiveMenuBar
from src.PySide.widgets import sl_menu_bar as menu_module
from src.PySide.window import main_window as main_window_module
from src.PySide.window.main_window import MainWindow
from src.core import app_state
from src.core import cache as cache_module
from src.core.constant import (
    CacheType,
    KEYRING_APP_SETTINGS,
    KEYRING_COOKIES,
    KEYRING_COOKIES_INDEX,
    KEYRING_ROOM_INFO,
    KEYRING_SERVICE_NAME,
    KEYRING_SETTINGS,
)
from src.core.credentials import CredentialStore, CredentialTransactionError
from src.core.workers import WorkerManager
from src.core.workers.base import BaseWorker, Presenter
from src.core.workers.credentials import credential_manager
from src.core.workers.credentials.credential_manager import (
    CredentialManagerWorker,
)
from tests.helpers import FakeKeyring

SERVICE = KEYRING_SERVICE_NAME
INDEX = KEYRING_COOKIES_INDEX


def nav(code: int) -> dict[str, object]:
    return {"code": code, "message": "fixture"}


def nav_ok(uid: str) -> dict[str, object]:
    return {
        "code": 0,
        "message": "0",
        "data": {
            "isLogin": True,
            "mid": int(uid),
            "uname": f"user-{uid}",
        },
    }


class FakeResponse:
    def __init__(self, payload: object):
        self.payload = payload
        self.encoding = None

    def raise_for_status(self) -> None:
        return None

    def json(self) -> object:
        return self.payload


class RequestSequence:
    def __init__(self, responses: list[object]):
        self.responses = list(responses)

    def __call__(self, *args, **kwargs) -> FakeResponse:
        if not self.responses:
            raise AssertionError("unexpected nav request")
        return FakeResponse(self.responses.pop(0))


class QtStateTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.saved_indices = list(app_state.cookie_indices)
        self.saved_usernames = dict(app_state.usernames)
        self.saved_cookies = dict(app_state.cookies_dict)
        self.saved_cookie_index = app_state.cookie_state.current_cookie_idx
        self.saved_scan_status = app_state.scan_status.as_dict()
        self.saved_room_info = app_state.room_info.as_dict()
        self.saved_stream_status = app_state.stream_status.as_dict()
        self.saved_obs_settings = app_state.obs_settings.as_dict()
        app_state.cookie_indices.clear()
        app_state.usernames.clear()
        app_state.cookies_dict.clear()
        app_state.cookie_state.current_cookie_idx = 0
        app_state.scan_status.reset()
        app_state.room_info.reset()
        app_state.stream_status.reset()
        app_state.obs_settings.reset()

    def tearDown(self):
        app_state.cookie_indices[:] = self.saved_indices
        app_state.usernames.clear()
        app_state.usernames.update(self.saved_usernames)
        app_state.cookies_dict.clear()
        app_state.cookies_dict.update(self.saved_cookies)
        app_state.cookie_state.current_cookie_idx = self.saved_cookie_index
        for state, saved in (
            (app_state.scan_status, self.saved_scan_status),
            (app_state.room_info, self.saved_room_info),
            (app_state.stream_status, self.saved_stream_status),
            (app_state.obs_settings, self.saved_obs_settings),
        ):
            state.reset()
            state.update(saved)
        QApplication.processEvents()


class MenuFixtureMixin:
    def setUp(self):
        super().setUp()
        self.keyring = FakeKeyring()
        self.patches = ExitStack()
        for owner, name, replacement in (
            (keyring, "get_password", self.keyring.get_password),
            (keyring, "set_password", self.keyring.set_password),
            (keyring, "delete_password", self.keyring.delete_password),
            (menu_module, "delete_password", self.keyring.delete_password),
        ):
            self.patches.enter_context(
                patch.object(owner, name, new=replacement)
            )
        self.store = CredentialStore(self.keyring)
        self.menu = StartLiveMenuBar()
        self.menu._store = self.store

    def tearDown(self):
        self.menu.deleteLater()
        self.patches.close()
        super().tearDown()

    @staticmethod
    def cookies(uid: str) -> dict[str, str]:
        return {"DedeUserID": uid, "SESSDATA": f"session-{uid}"}

    def seed_accounts(self, *uids: str) -> None:
        for uid in uids:
            self.keyring.put(f"cookies|{uid}", self.cookies(uid))
        self.keyring.put(INDEX, [f"cookies|{uid}" for uid in uids])
        self.store.load_index()
        self.menu._populate_account_menu()

    def persisted_index(self) -> list[str]:
        raw = self.keyring.values.get((SERVICE, INDEX))
        return [] if raw is None else loads(raw)

    def account_action(self, index: int) -> QAction:
        return next(
            action
            for action in self.menu.account_group.actions()
            if action.data() == index
        )

    @staticmethod
    def make_switch_ready() -> None:
        app_state.scan_status.update(
            {
                "scanned": True,
                "area_updated": True,
                "room_updated": True,
                "const_updated": True,
                "announce_updated": True,
            }
        )

    def account_indices_in_menu(self) -> list[int]:
        return [
            action.data()
            for action in self.menu.account_group.actions()
        ]


class CredentialMenuTests(MenuFixtureMixin, QtStateTestCase):

    def test_account_switch_emits_target_without_precommitting_current_index(self):
        self.seed_accounts("1", "2")
        app_state.cookie_state.current_cookie_idx = 0
        self.make_switch_ready()
        spy = QSignalSpy(self.menu.accountSwitch)

        self.account_action(1).trigger()

        self.assertEqual(spy.count(), 1)
        self.assertEqual(spy.at(0), [1])
        self.assertEqual(app_state.cookie_state.current_cookie_idx, 0)

    def test_add_account_emits_intent_without_moving_active_index(self):
        self.seed_accounts("1", "2")
        app_state.cookie_state.current_cookie_idx = 0
        spy = QSignalSpy(self.menu.accountAdded)

        self.menu._add_new_account()

        self.assertEqual(spy.count(), 1)
        self.assertEqual(app_state.cookie_state.current_cookie_idx, 0)

    def test_manual_logout_middle_account_prefers_previous_item(self):
        self.seed_accounts("1", "2", "3")
        app_state.cookie_state.current_cookie_idx = 1
        app_state.cookies_dict.update(self.cookies("2"))
        app_state.scan_status["scanned"] = True
        spy = QSignalSpy(self.menu.cookieDeleted)

        result = self.menu.delete_cookies()

        self.assertEqual(result, (0, False))
        self.assertEqual(spy.count(), 1)
        self.assertEqual(spy.at(0), [0, False])
        self.assertEqual(self.persisted_index(), ["cookies|1", "cookies|3"])

    def test_manual_logout_only_account_emits_empty_result(self):
        self.seed_accounts("1")
        app_state.cookie_state.current_cookie_idx = 0
        app_state.cookies_dict.update(self.cookies("1"))
        app_state.scan_status["scanned"] = True
        spy = QSignalSpy(self.menu.cookieDeleted)

        result = self.menu.delete_cookies()

        self.assertEqual(result, (0, True))
        self.assertEqual(spy.at(0), [0, True])
        self.assertEqual(self.persisted_index(), [])

    def test_manual_logout_final_position_emits_previous_target(self):
        self.seed_accounts("1", "2", "3")
        app_state.cookie_state.current_cookie_idx = 2
        app_state.cookies_dict.update(self.cookies("3"))
        app_state.scan_status["scanned"] = True
        spy = QSignalSpy(self.menu.cookieDeleted)

        result = self.menu.delete_cookies()

        self.assertEqual(result, (1, False))
        self.assertEqual(spy.at(0), [1, False])
        self.assertEqual(self.persisted_index(), ["cookies|1", "cookies|2"])

    def test_manual_logout_removes_deleted_accounts_title_cache(self):
        self.seed_accounts("1", "2")
        app_state.cookie_state.current_cookie_idx = 1
        app_state.cookies_dict.update(self.cookies("2"))
        app_state.scan_status["scanned"] = True

        with TemporaryDirectory() as temp_dir, patch.dict(
            cache_module._cache_dir,
            {CacheType.CONFIG: Path(temp_dir)},
            clear=False,
        ):
            title_cache = Path(temp_dir) / "title2"
            title_cache.write_text("fixture", encoding="utf-8")

            self.menu.delete_cookies()

            self.assertFalse(title_cache.exists())

    def test_manual_logout_store_failure_does_not_emit_or_rebuild(self):
        self.seed_accounts("1", "2")
        app_state.cookie_state.current_cookie_idx = 1
        app_state.cookies_dict.update(self.cookies("2"))
        app_state.scan_status["scanned"] = True
        before_actions = self.account_indices_in_menu()
        self.keyring.failures[("set", INDEX)] = RuntimeError(
            "index unavailable"
        )
        spy = QSignalSpy(self.menu.cookieDeleted)

        caught = None
        try:
            self.menu.delete_cookies()
        except Exception as error:
            caught = error

        self.assertIsInstance(caught, CredentialTransactionError)
        self.assertEqual(spy.count(), 0)
        self.assertEqual(self.account_indices_in_menu(), before_actions)
        self.assertEqual(self.persisted_index(), ["cookies|1", "cookies|2"])
        self.assertIsNotNone(
            self.keyring.values.get((SERVICE, "cookies|2"))
        )
        self.assertEqual(app_state.cookie_state.current_cookie_idx, 1)

    def test_manual_logout_invalid_indices_do_not_delete_credentials(self):
        for current in (-1, 2):
            with self.subTest(current=current):
                app_state.cookie_indices.clear()
                app_state.usernames.clear()
                app_state.cookies_dict.clear()
                self.seed_accounts("1", "2")
                app_state.cookie_state.current_cookie_idx = current
                app_state.cookies_dict.update(self.cookies("1"))
                spy = QSignalSpy(self.menu.cookieDeleted)

                result = self.menu.delete_cookies()

                self.assertIsNone(result)
                self.assertEqual(spy.count(), 0)
                self.assertEqual(
                    self.persisted_index(), ["cookies|1", "cookies|2"]
                )
                self.assertIsNotNone(
                    self.keyring.values.get((SERVICE, "cookies|1"))
                )
                self.assertEqual(app_state.cookies_dict, {})
                self.assertEqual(app_state.cookie_state.current_cookie_idx, 2)

    def test_manual_logout_missing_index_does_not_delete_orphan(self):
        self.keyring.put("cookies|1", self.cookies("1"))
        app_state.cookie_indices[:] = ["cookies|1"]
        app_state.usernames["cookies|1"] = "one"
        app_state.cookies_dict.update(self.cookies("1"))
        app_state.cookie_state.current_cookie_idx = 0
        self.menu._populate_account_menu()
        spy = QSignalSpy(self.menu.cookieDeleted)

        result = self.menu.delete_cookies()

        self.assertIsNone(result)
        self.assertEqual(spy.count(), 0)
        self.assertIsNotNone(
            self.keyring.values.get((SERVICE, "cookies|1"))
        )
        self.assertEqual(app_state.cookie_indices, [])
        self.assertEqual(self.account_indices_in_menu(), [])
        self.assertEqual(app_state.cookie_state.current_cookie_idx, 0)

    def test_manual_logout_cache_mismatch_reconciles_without_deleting(self):
        self.seed_accounts("1", "2")
        app_state.cookie_indices[:] = ["cookies|2", "cookies|1"]
        app_state.usernames.update(
            {"cookies|2": "two", "cookies|1": "one"}
        )
        app_state.cookies_dict.update(self.cookies("2"))
        app_state.cookie_state.current_cookie_idx = 0
        self.menu._populate_account_menu()
        spy = QSignalSpy(self.menu.cookieDeleted)

        result = self.menu.delete_cookies()

        self.assertIsNone(result)
        self.assertEqual(spy.count(), 0)
        self.assertEqual(self.persisted_index(), ["cookies|1", "cookies|2"])
        self.assertIsNotNone(
            self.keyring.values.get((SERVICE, "cookies|1"))
        )
        self.assertIsNotNone(
            self.keyring.values.get((SERVICE, "cookies|2"))
        )
        self.assertEqual(app_state.cookie_indices, ["cookies|1", "cookies|2"])
        self.assertEqual(app_state.cookie_state.current_cookie_idx, 2)
        self.assertEqual(self.account_indices_in_menu(), [0, 1])

    def test_title_cache_failure_does_not_block_committed_logout_signal(self):
        self.seed_accounts("1", "2")
        app_state.cookie_state.current_cookie_idx = 1
        app_state.cookies_dict.update(self.cookies("2"))
        spy = QSignalSpy(self.menu.cookieDeleted)

        def fail_cache_cleanup(_uid: str):
            raise OSError("CACHE_SECRET_CANARY")

        with patch.object(
                menu_module, "del_cache_user", new=fail_cache_cleanup
        ), self.assertLogs(self.menu.logger.logger, level="WARNING") as logs:
            result = self.menu.delete_cookies()

        self.assertEqual(result, (0, False))
        self.assertEqual(spy.at(0), [0, False])
        self.assertEqual(self.persisted_index(), ["cookies|1"])
        self.assertNotIn("CACHE_SECRET_CANARY", "\n".join(logs.output))

    def test_clear_all_uses_store_and_preserves_existing_global_clear_policy(self):
        self.seed_accounts("1", "2")
        for key in (
            KEYRING_COOKIES,
            KEYRING_ROOM_INFO,
            KEYRING_SETTINGS,
            KEYRING_APP_SETTINGS,
        ):
            self.keyring.put(key, {"fixture": key})
        spy = QSignalSpy(self.menu.credDeleted)

        with TemporaryDirectory() as temp_dir, patch.object(
            menu_module,
            "cache_base_dir",
            new=lambda _kind: Path(temp_dir) / "missing",
        ):
            self.menu._delete_cred()

        for key in (
            "cookies|1",
            "cookies|2",
            INDEX,
            KEYRING_COOKIES,
            KEYRING_ROOM_INFO,
            KEYRING_SETTINGS,
            KEYRING_APP_SETTINGS,
        ):
            self.assertIsNone(self.keyring.values.get((SERVICE, key)))
        self.assertEqual(spy.count(), 1)
        self.assertEqual(spy.at(0), [True])

    def test_expired_selected_account_is_pruned_by_manager_without_menu_delete(self):
        self.seed_accounts("1", "2", "3")
        app_state.cookie_state.current_cookie_idx = 0
        app_state.cookies_dict.update(self.cookies("1"))
        self.make_switch_ready()
        switch_spy = QSignalSpy(self.menu.accountSwitch)
        delete_spy = QSignalSpy(self.menu.cookieDeleted)

        self.account_action(2).trigger()

        self.assertEqual(switch_spy.count(), 1)
        self.assertEqual(switch_spy.at(0), [2])
        target = switch_spy.at(0)[0]
        worker = CredentialManagerWorker(None, target)
        worker._store = self.store
        worker._session.get = RequestSequence([nav(-101), nav_ok("2")])
        with patch.object(
            credential_manager, "get_password", new=lambda *_args: None
        ), patch.object(
            credential_manager, "delete_password", new=lambda *_args: None
        ):
            result = worker.run(None)

        self.assertEqual(result, 1)
        self.assertEqual(delete_spy.count(), 0)
        self.assertEqual(self.persisted_index(), ["cookies|1", "cookies|2"])
        self.assertEqual(app_state.cookie_state.current_cookie_idx, 1)
        self.assertEqual(app_state.cookies_dict["DedeUserID"], "2")


class PanelStub(QWidget):
    class ObsButtonState(QObject):
        obsDisconnected = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.obs_btn_state = self.ObsButtonState(self)
        self.start_count = 0
        self.stop_count = 0
        self.host_input = QLineEdit(self)
        self.port_input = QLineEdit(self)
        self.pass_input = QLineEdit(self)
        self.obs_auto_live_checkbox = QCheckBox(self)
        self.obs_auto_connect_checkbox = QCheckBox(self)

    def start_live(self, _checked=False):
        self.start_count += 1

    def stop_live(self, _checked=False):
        self.stop_count += 1


class SideBarStub(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.btn_home = QCheckBox(self)


class SetupWindowHarness(QMainWindow):
    def __init__(self, *, with_panel: bool = True):
        super().__init__()
        self.logger = logging.getLogger("SetupWindowHarness")
        self.panel = PanelStub(self) if with_panel else None
        self.old_panel = self.panel
        self.tray_start_live_action = QAction(self)
        self.tray_stop_live_action = QAction(self)
        if self.panel is not None:
            self.tray_start_live_action.triggered.connect(self.panel.start_live)
            self.tray_stop_live_action.triggered.connect(self.panel.stop_live)
        self._stack = QStackedWidget(self)
        self._side_bar = SideBarStub(self)
        self._log_viewer = QWidget(self)
        self._settings_page = QWidget(self)
        self._no_const_update = True
        self.restart_snapshots: list[tuple[dict[str, str], int]] = []
        self.submitted: list[object] = []

    def _restart_thread_manager(self):
        self.restart_snapshots.append(
            (
                dict(app_state.cookies_dict),
                app_state.cookie_state.current_cookie_idx,
            )
        )

    def add_thread(self, worker, /, on_progress=False):
        self.submitted.append(worker)

    def _post_scan_setup(self):
        return None

    def load_credentials(self):
        return None

    def _qr_expired(self):
        return None

    def _qr_not_confirmed(self):
        return None

    def _new_version_hint(self, _version):
        return None


class ServerSignals(QObject):
    startLive = Signal()
    stopLive = Signal()


class RouteSignalStub:
    def __init__(self, *, fail_first_disconnect: bool = False):
        self._slots = []
        self._fail_first_disconnect = fail_first_disconnect

    def connect(self, slot):
        self._slots.append(slot)

    def disconnect(self, slot):
        if self._fail_first_disconnect:
            self._fail_first_disconnect = False
            raise RuntimeError("receiver already deleted")
        self._slots.remove(slot)

    def emit(self):
        for slot in list(self._slots):
            slot()


class ActionStub:
    def __init__(self, *, fail_first_disconnect: bool = False):
        self.triggered = RouteSignalStub(
            fail_first_disconnect=fail_first_disconnect
        )
        self.enabled = True

    def setEnabled(self, enabled: bool):
        self.enabled = enabled

    def trigger(self):
        self.triggered.emit()


class ServerStub:
    def __init__(self):
        self.signals = ServerSignals()


class PassivePresenter(Presenter):
    def prepare_success_view(self, *args, **kwargs):
        return None

    def prepare_fail_view(self, exception: Exception):
        return None

    def prepare_progress_view(self, *args, **kwargs):
        return None


class ImmediateWorker(BaseWorker):
    def __init__(self, presenter: Presenter):
        super().__init__(name="queued-old-generation", with_session=False,
                         presenter=presenter)

    def run(self, report_progress, *args, **kwargs):
        return "old-result"


class FollowupWorker(BaseWorker):
    def __init__(self, deliveries: list[str]):
        super().__init__(name="stale-followup", with_session=False)
        self._deliveries = deliveries

    def run(self, report_progress, *args, **kwargs):
        self._deliveries.append("followup-ran")


class StaleFollowupPresenter(Presenter):
    def __init__(self, view, deliveries: list[str]):
        super().__init__()
        self._view = view
        self._deliveries = deliveries

    def prepare_success_view(self, *args, **kwargs):
        self._deliveries.append("old-presenter-ran")
        self._view.add_thread(FollowupWorker(self._deliveries))

    def prepare_fail_view(self, exception: Exception):
        self._deliveries.append("old-presenter-failed")

    def prepare_progress_view(self, *args, **kwargs):
        return None


class TrackingDispatcher(GUIDispatcher):
    def __init__(self):
        super().__init__()
        self.finalize_posted = Event()

    def post(self, fn, *args, **kwargs):
        super().post(fn, *args, **kwargs)
        if getattr(fn, "__name__", "") == "finalize":
            self.finalize_posted.set()


class GenerationWindowHarness(SetupWindowHarness):
    def __init__(self):
        super().__init__()
        self._gui_dispatcher = TrackingDispatcher()
        self._gui_presenter = PassivePresenter()
        self._thread_manager = WorkerManager(
            self._gui_dispatcher, max_workers=1
        )

    def _restart_thread_manager(self):
        MainWindow._restart_thread_manager(self)

    def add_thread(self, worker, /, on_progress=False):
        if isinstance(worker, CredentialManagerWorker):
            self.submitted.append(worker)
            return None
        return MainWindow.add_thread(self, worker, on_progress=on_progress)


class MainWindowLifecycleTests(QtStateTestCase):
    def test_setup_ui_hands_explicit_target_to_new_generation_after_teardown(self):
        app_state.cookie_indices[:] = [
            "cookies|1",
            "cookies|2",
            "cookies|3",
        ]
        app_state.cookie_state.current_cookie_idx = 0
        app_state.cookies_dict.update(
            {"DedeUserID": "1", "SESSDATA": "session-1"}
        )
        window = SetupWindowHarness()

        caught = None
        try:
            with patch.object(
                main_window_module, "StreamConfigPanel", new=PanelStub
            ):
                MainWindow.setup_ui(window, cookie_index=2)
        except Exception as error:
            caught = error

        self.assertIsNone(caught)
        self.assertEqual(
            window.restart_snapshots,
            [({"DedeUserID": "1", "SESSDATA": "session-1"}, 0)],
        )
        self.assertEqual(app_state.cookies_dict, {})
        self.assertEqual(app_state.cookie_state.current_cookie_idx, 3)
        self.assertEqual(window._credential_target_idx, 2)
        self.assertEqual(window.credential_worker.cookie_index, 2)
        self.assertIs(window.submitted[-1], window.credential_worker)

        window.tray_start_live_action.trigger()
        self.assertEqual(window.old_panel.start_count, 0)
        self.assertEqual(window.panel.start_count, 1)
        window.deleteLater()

    def test_partial_tray_disconnect_does_not_abort_reconstruction(self):
        app_state.cookie_indices[:] = ["cookies|1"]
        app_state.cookie_state.current_cookie_idx = 0
        app_state.cookies_dict.update(
            {"DedeUserID": "1", "SESSDATA": "session-1"}
        )
        window = SetupWindowHarness()
        window.tray_start_live_action = ActionStub(
            fail_first_disconnect=True
        )

        caught = None
        try:
            with patch.object(
                    main_window_module, "StreamConfigPanel", new=PanelStub
            ):
                MainWindow.setup_ui(window, cookie_index=0)
        except Exception as error:
            caught = error

        self.assertIsNone(caught)
        self.assertEqual(len(window.restart_snapshots), 1)
        self.assertEqual(app_state.cookies_dict, {})
        self.assertEqual(app_state.cookie_state.current_cookie_idx, 1)
        window.tray_start_live_action.trigger()
        self.assertEqual(window.old_panel.start_count, 0)
        self.assertEqual(window.panel.start_count, 1)
        window.deleteLater()

    def test_existing_http_server_routes_only_to_reconstructed_panel(self):
        app_state.cookie_indices[:] = ["cookies|1"]
        app_state.cookie_state.current_cookie_idx = 0
        window = SetupWindowHarness()
        server = ServerStub()
        window._server_thread = server
        server.signals.startLive.connect(window.old_panel.start_live)
        server.signals.stopLive.connect(window.old_panel.stop_live)

        with patch.object(
                main_window_module, "StreamConfigPanel", new=PanelStub
        ):
            MainWindow.setup_ui(window, cookie_index=0)

        server.signals.startLive.emit()
        server.signals.stopLive.emit()
        self.assertEqual(window.old_panel.start_count, 0)
        self.assertEqual(window.old_panel.stop_count, 0)
        self.assertEqual(window.panel.start_count, 1)
        self.assertEqual(window.panel.stop_count, 1)
        window.deleteLater()

    def test_first_setup_without_panel_or_server_reconstructs_once(self):
        window = SetupWindowHarness(with_panel=False)

        with patch.object(
                main_window_module, "StreamConfigPanel", new=PanelStub
        ):
            MainWindow.setup_ui(window, cookie_index=0)

        self.assertEqual(window.restart_snapshots, [])
        self.assertIsInstance(window.panel, PanelStub)
        self.assertIs(window.submitted[-1], window.credential_worker)
        window.deleteLater()

    def test_queued_old_generation_finalizer_cannot_submit_to_new_manager(self):
        app_state.cookie_indices[:] = ["cookies|1", "cookies|2"]
        app_state.cookie_state.current_cookie_idx = 0
        app_state.cookies_dict.update(
            {"DedeUserID": "1", "SESSDATA": "session-1"}
        )
        window = GenerationWindowHarness()
        deliveries: list[str] = []
        old_dispatcher = window._gui_dispatcher
        old_manager = window._thread_manager
        stale_presenter = StaleFollowupPresenter(window, deliveries)
        future = old_manager.submit(ImmediateWorker(stale_presenter))
        future.result(timeout=1)
        self.assertTrue(old_dispatcher.finalize_posted.wait(timeout=1))

        with patch.object(
                main_window_module, "StreamConfigPanel", new=PanelStub
        ):
            MainWindow.setup_ui(window, cookie_index=1)
        QApplication.processEvents()

        self.assertEqual(deliveries, [])
        self.assertIsNot(window._thread_manager, old_manager)
        self.assertIsNot(window._gui_dispatcher, old_dispatcher)
        window._gui_dispatcher.close()
        window._thread_manager.shutdown(wait=True)
        window.deleteLater()


class LoadCredentialsHarness:
    def __init__(self, menu: StartLiveMenuBar, target: int):
        self.logger = logging.getLogger("LoadCredentialsHarness")
        self.menu_bar = menu
        self.login_label = QLabel()
        self.status_label = ClickableLabel()
        self._credential_target_idx = target
        self.qr_fetches = 0
        self.post_scan_calls = 0
        self.retry_targets: list[tuple[int | None, bool]] = []
        self._credential_result_handled = False

    def _fetch_qr(self):
        self.qr_fetches += 1

    def _post_scan_setup(self):
        self.post_scan_calls += 1

    def setup_ui(
        self, *, is_new: bool = False, cookie_index: int | None = None
    ):
        self.retry_targets.append((cookie_index, is_new))


class CredentialLoadRoutingTests(MenuFixtureMixin, QtStateTestCase):
    def test_empty_manager_result_starts_qr_once(self):
        window = LoadCredentialsHarness(self.menu, target=0)
        app_state.scan_status["is_new"] = True

        MainWindow.load_credentials(window)

        self.assertEqual(window.qr_fetches, 1)
        self.assertEqual(window.post_scan_calls, 0)

    def test_repeated_empty_manager_delivery_starts_qr_exactly_once(self):
        window = LoadCredentialsHarness(self.menu, target=0)
        app_state.scan_status["is_new"] = True

        MainWindow.load_credentials(window)
        MainWindow.load_credentials(window)

        self.assertEqual(window.qr_fetches, 1)
        self.assertEqual(window.post_scan_calls, 0)

    def test_transient_failure_keeps_store_and_retries_same_target(self):
        self.seed_accounts("1", "2", "3")
        app_state.cookie_state.move_to_end()
        window = LoadCredentialsHarness(self.menu, target=2)
        before = self.persisted_index()
        delete_spy = QSignalSpy(self.menu.cookieDeleted)

        MainWindow.load_credentials(window)
        window.status_label.clicked.emit()

        self.assertEqual(delete_spy.count(), 0)
        self.assertEqual(self.persisted_index(), before)
        self.assertEqual(window.retry_targets, [(2, False)])
        self.assertIn("重试", window.login_label.text())

    def test_legacy_expired_flag_is_retryable_and_does_not_delete(self):
        self.seed_accounts("1", "2")
        app_state.cookie_state.current_cookie_idx = 0
        app_state.scan_status["expired"] = True
        window = LoadCredentialsHarness(self.menu, target=1)
        before = self.persisted_index()
        delete_spy = QSignalSpy(self.menu.cookieDeleted)

        MainWindow.load_credentials(window)
        window.status_label.clicked.emit()

        self.assertEqual(delete_spy.count(), 0)
        self.assertEqual(self.persisted_index(), before)
        self.assertEqual(window.qr_fetches, 0)
        self.assertEqual(window.retry_targets, [(1, False)])


class PresenterView:
    def __init__(self, menu: StartLiveMenuBar):
        self.menu_bar = menu
        self.panel = PanelStub()
        self.submitted: list[object] = []

    def add_thread(self, worker, /, on_progress=False):
        self.submitted.append(worker)


class CredentialPresenterTests(MenuFixtureMixin, QtStateTestCase):
    def test_failure_presenter_refreshes_menu_from_committed_store_state(self):
        self.seed_accounts("1", "2", "3")
        self.store.remove("cookies|3")
        view = PresenterView(self.menu)
        presenter = CredentialManagerPresenter(view, LoginState())

        presenter.prepare_fail_view(RuntimeError("temporary failure"))

        self.assertEqual(self.account_indices_in_menu(), [0, 1])
        view.panel.deleteLater()


if __name__ == "__main__":
    unittest.main()
