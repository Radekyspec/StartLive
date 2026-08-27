from json import dumps, loads
import unittest
from unittest.mock import patch

from requests import HTTPError, RequestException
from requests.utils import dict_from_cookiejar

from src.core import app_state
from src.core.app_state import create_session
from src.core.constant import (
    HeadersType,
    KEYRING_COOKIES_INDEX,
    KEYRING_SETTINGS,
    KEYRING_SERVICE_NAME,
)
from src.core.credentials import (
    CredentialStore,
    CredentialTransactionError,
)
from src.core.workers.base import BaseWorker
from src.core.workers.credentials import credential_manager
from src.core.workers.credentials.credential_manager import (
    CredentialManagerWorker,
    CredentialValidationError,
)
from tests.helpers import FakeKeyring


SERVICE = KEYRING_SERVICE_NAME
INDEX = KEYRING_COOKIES_INDEX


def nav(code: int) -> dict[str, object]:
    return {"code": code, "message": "fixture"}


def nav_ok(uid: str, *, is_login: bool = True) -> dict[str, object]:
    return {
        "code": 0,
        "message": "0",
        "data": {
            "isLogin": is_login,
            "mid": int(uid),
            "uname": f"user-{uid}",
        },
    }


class FakeResponse:
    def __init__(
        self,
        payload: object,
        *,
        status_code: int = 200,
        json_error: Exception | None = None,
    ):
        self.payload = payload
        self.status_code = status_code
        self.json_error = json_error
        self.encoding = None

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise HTTPError(f"HTTP {self.status_code}", response=self)

    def json(self) -> object:
        if self.json_error is not None:
            raise self.json_error
        return self.payload


class RequestSequence:
    def __init__(self, session, responses: list[object]):
        self.session = session
        self.responses = list(responses)
        self.cookie_jars: list[dict[str, str]] = []

    def __call__(self, *args, **kwargs):
        self.cookie_jars.append(dict_from_cookiejar(self.session.cookies))
        if not self.responses:
            raise AssertionError("unexpected nav request")
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        leak = None
        if isinstance(response, tuple):
            response, leak = response
        if leak is not None:
            self.session.cookies.set("response_only", leak)
        if isinstance(response, FakeResponse):
            return response
        return FakeResponse(response)


class FailingReadKeyring(FakeKeyring):
    def __init__(self):
        super().__init__()
        self.read_failures: dict[str, Exception] = {}
        self.scheduled_read_failures: dict[str, tuple[int, Exception]] = {}
        self.read_counts: dict[str, int] = {}

    def fail_read_on_call(
        self, key: str, call: int, error: Exception
    ) -> None:
        self.scheduled_read_failures[key] = (call, error)

    def get_password(self, service: str, key: str) -> str | None:
        if error := self.read_failures.pop(key, None):
            raise error
        self.read_counts[key] = self.read_counts.get(key, 0) + 1
        scheduled = self.scheduled_read_failures.get(key)
        if scheduled is not None and self.read_counts[key] == scheduled[0]:
            raise scheduled[1]
        return super().get_password(service, key)


class CredentialManagerTests(unittest.TestCase):
    def setUp(self):
        self.keyring = FailingReadKeyring()
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
        self.get_password_patch = patch.object(
            credential_manager, "get_password", return_value=None
        )
        self.delete_password_patch = patch.object(
            credential_manager, "delete_password", return_value=None
        )
        self.get_password_mock = self.get_password_patch.start()
        self.delete_password_patch.start()

    def tearDown(self):
        self.delete_password_patch.stop()
        self.get_password_patch.stop()
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

    @staticmethod
    def cookies(uid: str, **extra: str) -> dict[str, str]:
        return {"DedeUserID": uid, "SESSDATA": f"session-{uid}", **extra}

    def seed_accounts(self, *uids: str) -> None:
        for uid in uids:
            self.keyring.put(f"cookies|{uid}", self.cookies(uid))
        self.keyring.put(INDEX, [f"cookies|{uid}" for uid in uids])

    def persisted_index(self) -> list[str]:
        raw = self.keyring.values.get((SERVICE, INDEX))
        return [] if raw is None else loads(raw)

    def worker(
        self, *, candidate: int, responses: list[object]
    ) -> CredentialManagerWorker:
        worker = CredentialManagerWorker(None, candidate)
        worker._store = CredentialStore(self.keyring)
        worker.requests = RequestSequence(worker._session, responses)
        worker._session.get = worker.requests
        return worker

    def test_cold_start_prunes_expired_first_account_then_loads_second(self):
        self.seed_accounts("1", "2")
        worker = self.worker(candidate=0, responses=[nav(-101), nav_ok("2")])

        self.assertEqual(worker.run(None), 0)
        self.assertEqual(self.persisted_index(), ["cookies|2"])
        self.assertEqual(app_state.cookies_dict["DedeUserID"], "2")
        self.assertEqual(app_state.cookie_state.current_cookie_idx, 0)

    def test_expired_final_candidate_clamps_to_remaining_final_item(self):
        self.seed_accounts("1", "2", "3")
        worker = self.worker(candidate=2, responses=[nav(-101), nav_ok("2")])

        self.assertEqual(worker.run(None), 1)
        self.assertEqual(
            self.persisted_index(), ["cookies|1", "cookies|2"]
        )
        self.assertEqual(app_state.cookies_dict["DedeUserID"], "2")

    def test_middle_deletion_keeps_numeric_candidate_for_original_next(self):
        self.seed_accounts("1", "2", "3")
        worker = self.worker(candidate=1, responses=[nav(-101), nav_ok("3")])

        self.assertEqual(worker.run(None), 1)
        self.assertEqual(
            self.persisted_index(), ["cookies|1", "cookies|3"]
        )
        self.assertEqual(app_state.cookies_dict["DedeUserID"], "3")

    def test_unknown_nonzero_code_preserves_every_credential(self):
        self.seed_accounts("1", "2")

        with self.assertRaises(CredentialValidationError):
            self.worker(candidate=0, responses=[nav(-412)]).run(None)

        self.assertEqual(
            self.persisted_index(), ["cookies|1", "cookies|2"]
        )

    def test_missing_code_preserves_every_credential(self):
        self.seed_accounts("1")

        with self.assertRaises(CredentialValidationError):
            self.worker(
                candidate=0, responses=[{"message": "no code"}]
            ).run(None)

        self.assertEqual(self.persisted_index(), ["cookies|1"])

    def test_all_expired_enters_no_credential_state(self):
        self.seed_accounts("1", "2")
        result = self.worker(
            candidate=0, responses=[nav(-101), nav(-101)]
        ).run(None)

        self.assertEqual(result, 0)
        self.assertEqual(self.persisted_index(), [])
        self.assertTrue(app_state.scan_status["is_new"])
        self.assertEqual(app_state.cookies_dict, {})
        self.assertTrue(app_state.cookie_state.is_exhausted())

    def test_corrupted_record_is_pruned_then_next_candidate_is_loaded(self):
        self.seed_accounts("1", "2")
        self.keyring.put("cookies|1", {"DedeUserID": "wrong"})
        worker = self.worker(candidate=0, responses=[nav_ok("2")])

        self.assertEqual(worker.run(None), 0)
        self.assertEqual(self.persisted_index(), ["cookies|2"])
        self.assertEqual(app_state.cookies_dict["DedeUserID"], "2")

    def test_explicit_logged_out_response_is_permanently_invalid(self):
        self.seed_accounts("1", "2")
        worker = self.worker(
            candidate=0,
            responses=[nav_ok("1", is_login=False), nav_ok("2")],
        )

        self.assertEqual(worker.run(None), 0)
        self.assertEqual(self.persisted_index(), ["cookies|2"])

    def test_returned_uid_mismatch_is_permanently_invalid(self):
        self.seed_accounts("1", "2")
        worker = self.worker(
            candidate=0, responses=[nav_ok("9"), nav_ok("2")]
        )

        self.assertEqual(worker.run(None), 0)
        self.assertEqual(self.persisted_index(), ["cookies|2"])

    def test_candidate_request_contains_no_previous_account_only_cookie(self):
        self.seed_accounts("2")
        app_state.cookies_dict.update(
            {"DedeUserID": "1", "old_only": "secret"}
        )
        worker = self.worker(candidate=0, responses=[nav_ok("2")])

        self.assertEqual(worker.run(None), 0)
        self.assertTrue(worker.requests.cookie_jars)
        request_jar = worker.requests.cookie_jars[0]
        self.assertNotIn("old_only", request_jar)
        self.assertEqual(request_jar["DedeUserID"], "2")

    def test_response_cookie_from_pruned_candidate_does_not_reach_next(self):
        self.seed_accounts("1", "2")
        worker = self.worker(
            candidate=0,
            responses=[(nav(-101), "leak"), nav_ok("2")],
        )

        self.assertEqual(worker.run(None), 0)
        self.assertEqual(len(worker.requests.cookie_jars), 2)
        self.assertNotIn("response_only", worker.requests.cookie_jars[1])
        self.assertEqual(worker.requests.cookie_jars[0]["DedeUserID"], "1")
        self.assertEqual(worker.requests.cookie_jars[1]["DedeUserID"], "2")

    def test_transport_http_and_json_failures_are_temporary(self):
        failures = (
            RequestException("network unavailable"),
            FakeResponse({}, status_code=503),
            FakeResponse({}, json_error=ValueError("bad json")),
        )
        for response in failures:
            with self.subTest(response=type(response).__name__):
                self.keyring = FailingReadKeyring()
                self.seed_accounts("1")
                with self.assertRaises(CredentialValidationError):
                    self.worker(candidate=0, responses=[response]).run(None)
                self.assertEqual(self.persisted_index(), ["cookies|1"])

    def test_success_payload_schema_failure_is_temporary(self):
        self.seed_accounts("1")

        with self.assertRaises(CredentialValidationError):
            self.worker(
                candidate=0,
                responses=[{"code": 0, "data": {"isLogin": True}}],
            ).run(None)

        self.assertEqual(self.persisted_index(), ["cookies|1"])

    def test_index_keyring_failure_is_temporary_and_preserves_state(self):
        self.seed_accounts("1")
        app_state.cookies_dict.update(self.cookies("previous"))
        app_state.cookie_state.current_cookie_idx = 0
        self.keyring.read_failures[INDEX] = RuntimeError("keyring offline")

        with self.assertRaises(CredentialValidationError):
            self.worker(candidate=0, responses=[]).run(None)

        self.assertEqual(self.persisted_index(), ["cookies|1"])
        self.assertEqual(
            app_state.cookies_dict["DedeUserID"], "previous"
        )
        self.assertEqual(app_state.cookie_state.current_cookie_idx, 0)

    def test_record_keyring_failure_is_temporary_and_not_pruned(self):
        self.seed_accounts("1")
        self.keyring.read_failures["cookies|1"] = RuntimeError(
            "keyring offline"
        )

        with self.assertRaises(CredentialValidationError):
            self.worker(candidate=0, responses=[]).run(None)

        self.assertEqual(self.persisted_index(), ["cookies|1"])

    def test_removal_index_read_failure_after_permanent_nav_is_temporary(self):
        self.seed_accounts("1")
        self.keyring.fail_read_on_call(
            INDEX, 3, RuntimeError("index read unavailable")
        )

        with self.assertRaises(Exception) as caught:
            self.worker(candidate=0, responses=[nav(-101)]).run(None)

        self.assertIsInstance(caught.exception, CredentialValidationError)
        self.assertEqual(self.persisted_index(), ["cookies|1"])

    def test_removal_record_read_failure_after_permanent_nav_is_temporary(self):
        self.seed_accounts("1")
        self.keyring.fail_read_on_call(
            "cookies|1", 2, RuntimeError("record read unavailable")
        )

        with self.assertRaises(Exception) as caught:
            self.worker(candidate=0, responses=[nav(-101)]).run(None)

        self.assertIsInstance(caught.exception, CredentialValidationError)
        self.assertEqual(self.persisted_index(), ["cookies|1"])

    def test_obs_settings_logs_never_include_password(self):
        canary = "OBS_PASSWORD_CANARY_7d3f"
        cases = ("active", "persisted")
        for source in cases:
            with self.subTest(source=source):
                app_state.obs_settings.reset()
                self.get_password_mock.reset_mock(
                    return_value=True, side_effect=True
                )
                if source == "active":
                    app_state.obs_settings.update({"password": canary})
                    self.get_password_mock.return_value = None
                else:
                    saved = app_state.obs_settings.as_dict()
                    saved["password"] = canary
                    self.get_password_mock.side_effect = (
                        lambda service, key, payload=dumps(saved):
                        payload if key == KEYRING_SETTINGS else None
                    )

                with self.assertLogs("StartLiveLogger", level="INFO") as logs:
                    self.worker(candidate=0, responses=[]).run(None)

                self.assertNotIn(canary, "\n".join(logs.output))

    def test_remove_failure_propagates_without_speculative_identity_change(self):
        self.seed_accounts("1")
        previous = self.cookies("previous")
        app_state.cookies_dict.update(previous)
        self.keyring.failures[("delete", "cookies|1")] = RuntimeError(
            "keyring offline"
        )
        worker = self.worker(candidate=0, responses=[nav(-101)])

        with self.assertRaises(CredentialTransactionError):
            worker.run(None)

        self.assertEqual(self.persisted_index(), ["cookies|1"])
        self.assertEqual(app_state.cookies_dict, previous)
        self.assertEqual(app_state.cookie_state.current_cookie_idx, 1)


class AnonymousSessionTests(unittest.TestCase):
    def setUp(self):
        self.saved_cookies = dict(app_state.cookies_dict)
        self.saved_indices = list(app_state.cookie_indices)
        self.saved_index = app_state.cookie_state.current_cookie_idx
        app_state.cookies_dict.clear()

    def tearDown(self):
        app_state.cookies_dict.clear()
        app_state.cookies_dict.update(self.saved_cookies)
        app_state.cookie_indices[:] = self.saved_indices
        app_state.cookie_state.current_cookie_idx = self.saved_index

    def test_create_session_can_skip_global_account_cookies(self):
        app_state.cookies_dict.update(
            {"DedeUserID": "1", "old_only": "secret"}
        )
        try:
            session = create_session(
                HeadersType.WEB, inherit_account_cookies=False
            )
        except TypeError as error:
            self.fail(f"anonymous session option is unavailable: {error}")

        cookies = dict_from_cookiejar(session.cookies)
        self.assertNotIn("DedeUserID", cookies)
        self.assertNotIn("old_only", cookies)
        self.assertEqual(cookies["appkey"], app_state.constant.APP_KEY)

    def test_base_worker_threads_anonymous_session_option(self):
        app_state.cookies_dict.update({"DedeUserID": "1"})
        try:
            worker = BaseWorker(
                "test", inherit_account_cookies=False
            )
        except TypeError as error:
            self.fail(f"base worker option is unavailable: {error}")

        self.assertNotIn(
            "DedeUserID", dict_from_cookiejar(worker._session.cookies)
        )

    def test_exhausted_state_accepts_out_of_range_sentinel(self):
        app_state.cookie_indices[:] = ["cookies|1"]
        app_state.cookie_state.current_cookie_idx = 2

        self.assertTrue(app_state.cookie_state.is_exhausted())

    def test_empty_index_uses_zero_as_exhausted_sentinel(self):
        app_state.cookie_indices.clear()
        app_state.cookie_state.current_cookie_idx = 0

        self.assertTrue(app_state.cookie_state.is_exhausted())


if __name__ == "__main__":
    unittest.main()
