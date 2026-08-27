import unittest
from contextlib import ExitStack
from json import loads
from unittest.mock import patch

from requests.cookies import cookiejar_from_dict
from requests.utils import dict_from_cookiejar

from src.core import app_state
from src.core.constant import (
    KEYRING_COOKIES_INDEX,
    KEYRING_SERVICE_NAME,
    LoginResult,
)
from src.core.credentials import CredentialStore, CredentialTransactionError
from src.core.workers.login import fetch_login
from src.core.workers.login.fetch_login import FetchLoginWorker
from src.core.workers.login.fetch_qr import FetchQRWorker
from src.core.workers.usernames import fetch_usernames
from src.core.workers.usernames.fetch_usernames import FetchUsernamesWorker
from src.PySide.interface_adapters.login import buvid_ticket_presenter
from src.PySide.interface_adapters.login.buvid_ticket_presenter import (
    TicketFetchPresenter,
)
from tests.helpers import FakeKeyring


SERVICE = KEYRING_SERVICE_NAME
INDEX = KEYRING_COOKIES_INDEX


class FakeResponse:
    def __init__(self, payload, cookies=None):
        self._payload = payload
        self.cookies = cookiejar_from_dict(cookies or {})
        self.encoding = None

    def json(self):
        return self._payload


class RequestSequence:
    def __init__(self, session, responses):
        self._session = session
        self._responses = list(responses)
        self.cookie_jars = []

    def __call__(self, *args, **kwargs):
        self.cookie_jars.append(dict_from_cookiejar(self._session.cookies))
        if not self._responses:
            raise AssertionError("unexpected request")
        response, response_cookie = self._responses.pop(0)
        if response_cookie is not None:
            self._session.cookies.set("response_only", response_cookie)
        return response


class FailingReadKeyring(FakeKeyring):
    def __init__(self):
        super().__init__()
        self.read_error = None
        self.read_errors = {}

    def get_password(self, service, key):
        if key in self.read_errors:
            raise self.read_errors[key]
        if self.read_error is not None:
            raise self.read_error
        return super().get_password(service, key)


class CredentialLoginTests(unittest.TestCase):
    def setUp(self):
        self.keyring = FakeKeyring()
        self.store = CredentialStore(self.keyring)
        self.saved_indices = list(app_state.cookie_indices)
        self.saved_usernames = dict(app_state.usernames)
        self.saved_cookies = dict(app_state.cookies_dict)
        self.saved_cookie_index = app_state.cookie_state.current_cookie_idx
        self.saved_scan_status = app_state.scan_status.as_dict()
        app_state.cookie_indices.clear()
        app_state.usernames.clear()
        app_state.cookies_dict.clear()
        app_state.cookie_state.current_cookie_idx = 0
        app_state.scan_status.reset()

    def tearDown(self):
        app_state.cookie_indices[:] = self.saved_indices
        app_state.usernames.clear()
        app_state.usernames.update(self.saved_usernames)
        app_state.cookies_dict.clear()
        app_state.cookies_dict.update(self.saved_cookies)
        app_state.cookie_state.current_cookie_idx = self.saved_cookie_index
        app_state.scan_status.reset()
        app_state.scan_status.update(self.saved_scan_status)

    @staticmethod
    def cookies(uid, **extra):
        return {
            "DedeUserID": uid,
            "SESSDATA": f"session-{uid}",
            "bili_jct": f"csrf-{uid}",
            **extra,
        }

    @staticmethod
    def nav(uid):
        return {
            "code": 0,
            "message": "0",
            "data": {"uname": f"user-{uid}", "mid": int(uid)},
        }

    def seed_accounts(self, *uids):
        for uid in uids:
            self.store.add(self.cookies(uid))

    def persisted_index(self):
        raw = self.keyring.values.get((SERVICE, INDEX))
        return [] if raw is None else loads(raw)

    def patch_stores(self):
        stack = ExitStack()
        stack.enter_context(patch.object(fetch_login, "CredentialStore",
                                         return_value=self.store))
        stack.enter_context(patch.object(fetch_usernames, "CredentialStore",
                                         return_value=self.store))
        stack.enter_context(patch.object(buvid_ticket_presenter,
                                         "CredentialStore",
                                         return_value=self.store))
        return stack

    def successful_qr_worker(self, uid):
        app_state.scan_status["qr_key"] = "opaque-qr-key"
        worker = FetchLoginWorker(None)
        worker._session.get = lambda *args, **kwargs: FakeResponse(
            {"code": 0, "message": "0", "data": {"code": 0}},
            self.cookies(uid),
        )
        return worker

    def test_qr_success_appends_and_selects_returned_index(self):
        self.seed_accounts("1", "2")

        with self.patch_stores():
            result = self.successful_qr_worker("3").run(None)

        self.assertEqual(result, LoginResult.SUCCESS)
        self.assertEqual(
            self.persisted_index(),
            ["cookies|1", "cookies|2", "cookies|3"],
        )
        self.assertEqual(app_state.cookie_state.current_cookie_idx, 2)
        self.assertEqual(app_state.cookies_dict["DedeUserID"], "3")

    def test_qr_persistence_failure_does_not_publish_new_account(self):
        self.seed_accounts("1")
        previous = self.cookies("1", previous_only="kept")
        app_state.cookies_dict.update(previous)
        self.keyring.failures[("set", INDEX)] = RuntimeError(
            "keyring unavailable"
        )

        with self.patch_stores(), self.assertRaises(CredentialTransactionError):
            self.successful_qr_worker("2").run(None)

        self.assertEqual(self.persisted_index(), ["cookies|1"])
        self.assertNotIn((SERVICE, "cookies|2"), self.keyring.values)
        self.assertEqual(app_state.cookies_dict, previous)
        self.assertEqual(app_state.cookie_state.current_cookie_idx, 0)
        self.assertFalse(app_state.scan_status["scanned"])

    def test_qr_acquisition_and_polling_sessions_are_anonymous(self):
        app_state.cookies_dict.update(
            self.cookies("1", active_account_only="secret")
        )

        workers = (FetchQRWorker(None), FetchLoginWorker(None))

        for worker in workers:
            with self.subTest(worker=type(worker).__name__):
                jar = dict_from_cookiejar(worker._session.cookies)
                self.assertNotIn("DedeUserID", jar)
                self.assertNotIn("SESSDATA", jar)
                self.assertNotIn("active_account_only", jar)

    def test_qr_response_details_are_not_logged(self):
        qr_secret = "QR_SECRET_CANARY_53e1"
        qr_url = "https://example.invalid/QR_URL_CANARY_8a91"
        worker = FetchQRWorker(None)
        worker._session.get = lambda *args, **kwargs: FakeResponse(
            {
                "code": 0,
                "message": "0",
                "data": {"qrcode_key": qr_secret, "url": qr_url},
            }
        )

        with self.assertLogs("StartLiveLogger", level="INFO") as logs:
            worker.run(None)

        output = "\n".join(logs.output)
        self.assertNotIn(qr_secret, output)
        self.assertNotIn(qr_url, output)

    def test_qr_poll_response_body_is_not_logged(self):
        response_canary = "QR_RESPONSE_CANARY_f49c"
        app_state.scan_status["qr_key"] = "opaque-qr-key"
        worker = FetchLoginWorker(None)
        responses = iter((
            FakeResponse({
                "code": 0,
                "message": response_canary,
                "data": {"code": 86101},
            }),
            FakeResponse({
                "code": 0,
                "message": "expired",
                "data": {"code": 86038},
            }),
        ))
        worker._session.get = lambda *args, **kwargs: next(responses)

        with patch.object(fetch_login, "sleep", return_value=None), \
                self.assertLogs("StartLiveLogger", level="INFO") as logs:
            self.assertEqual(worker.run(None), LoginResult.QR_EXPIRED)

        self.assertNotIn(response_canary, "\n".join(logs.output))

    def test_ticket_refresh_updates_in_place_without_changing_selection(self):
        self.seed_accounts("1", "2")
        app_state.cookies_dict.update(self.cookies("1", bili_ticket="new"))
        app_state.cookie_state.current_cookie_idx = 1

        with self.patch_stores():
            TicketFetchPresenter().prepare_success_view()

        self.assertEqual(self.persisted_index(), ["cookies|1", "cookies|2"])
        self.assertEqual(self.store.read("cookies|1")["bili_ticket"], "new")
        self.assertEqual(app_state.cookie_state.current_cookie_idx, 1)

    def test_ticket_refresh_store_failure_propagates_without_reordering(self):
        self.seed_accounts("1", "2")
        app_state.cookies_dict.update(self.cookies("1", bili_ticket="new"))
        app_state.cookie_state.current_cookie_idx = 1
        self.keyring.failures[("set", "cookies|1")] = RuntimeError(
            "keyring unavailable"
        )

        with self.patch_stores(), self.assertRaises(CredentialTransactionError):
            TicketFetchPresenter().prepare_success_view()

        self.assertEqual(self.persisted_index(), ["cookies|1", "cookies|2"])
        self.assertEqual(app_state.cookie_state.current_cookie_idx, 1)

    def test_username_refresh_restores_anonymous_jar_for_every_account(self):
        self.store.add(self.cookies("1", one_only="x"))
        self.store.add(self.cookies("2"))
        app_state.cookies_dict.update(
            self.cookies("9", active_account_only="must-not-leak")
        )
        app_state.scan_status["scanned"] = True

        with self.patch_stores(), \
                patch.object(fetch_usernames, "sleep", return_value=None):
            worker = FetchUsernamesWorker("")
            requests = RequestSequence(worker._session, [
                (FakeResponse(self.nav("1")), "from-first-response"),
                (FakeResponse(self.nav("2")), None),
            ])
            worker._session.get = requests
            worker.run(None)

        self.assertEqual(len(requests.cookie_jars), 2)
        first, second = requests.cookie_jars
        self.assertEqual(first["DedeUserID"], "1")
        self.assertIn("one_only", first)
        self.assertEqual(second["DedeUserID"], "2")
        self.assertNotIn("one_only", second)
        self.assertNotIn("response_only", second)
        self.assertNotIn("active_account_only", first)
        self.assertNotIn("active_account_only", second)

    def test_username_store_failure_propagates_without_changing_names(self):
        failing = FailingReadKeyring()
        store = CredentialStore(failing)
        app_state.usernames["cookies|1"] = "unchanged"
        app_state.scan_status["scanned"] = True
        failing.read_error = RuntimeError("keyring unavailable")

        with patch.object(fetch_usernames, "CredentialStore",
                          return_value=store), \
                patch.object(fetch_usernames, "sleep", return_value=None), \
                self.assertRaises(RuntimeError):
            worker = FetchUsernamesWorker("")
            worker.run(None)

        self.assertEqual(app_state.usernames, {"cookies|1": "unchanged"})

    def test_late_username_store_failure_publishes_no_partial_names(self):
        failing = FailingReadKeyring()
        store = CredentialStore(failing)
        store.add(self.cookies("1"))
        store.add(self.cookies("2"))
        previous = {
            "cookies|1": "unchanged-one",
            "cookies|2": "unchanged-two",
        }
        app_state.usernames.clear()
        app_state.usernames.update(previous)
        app_state.scan_status["scanned"] = True
        failing.read_errors["cookies|2"] = RuntimeError(
            "keyring unavailable"
        )

        with patch.object(fetch_usernames, "CredentialStore",
                          return_value=store), \
                patch.object(fetch_usernames, "sleep", return_value=None):
            worker = FetchUsernamesWorker("")
            worker._session.get = lambda *args, **kwargs: FakeResponse(
                self.nav("1")
            )
            with self.assertRaises(RuntimeError):
                worker.run(None)

        self.assertEqual(app_state.usernames, previous)


if __name__ == "__main__":
    unittest.main()
