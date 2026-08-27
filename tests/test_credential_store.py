import unittest
from json import dumps, loads

from src.core import app_state
from src.core.constant import (
    KEYRING_COOKIES,
    KEYRING_COOKIES_INDEX,
    KEYRING_ROOM_INFO,
    KEYRING_SERVICE_NAME,
)
from src.core.credentials.store import (
    CredentialIndexCorruptedError,
    CredentialRecordCorruptedError,
    CredentialStore,
    CredentialTransactionError,
)
from tests.helpers import FakeKeyring

SERVICE = KEYRING_SERVICE_NAME
INDEX = KEYRING_COOKIES_INDEX
LEGACY = KEYRING_COOKIES


class TransactionKeyring(FakeKeyring):
    """Fake keyring whose next selected mutation can fail."""

    def __init__(self, *, reject_missing_deletes: bool = False):
        super().__init__()
        self.reject_missing_deletes = reject_missing_deletes

    def fail_next(self, operation: str, key: str, error: Exception) -> None:
        self.failures[(operation, key)] = error

    def put_raw(self, key: str, value: str) -> None:
        self.values[(SERVICE, key)] = value

    def delete_password(self, service: str, key: str) -> None:
        if self.reject_missing_deletes and (service, key) not in self.values:
            raise RuntimeError(f"no credential stored for {key}")
        super().delete_password(service, key)


class CredentialStateTestCase(unittest.TestCase):
    def setUp(self):
        self.keyring = FakeKeyring()
        self.original_indices = list(app_state.cookie_indices)
        self.original_usernames = dict(app_state.usernames)
        self.original_cookies = dict(app_state.cookies_dict)
        self.original_index = app_state.cookie_state.current_cookie_idx
        app_state.cookie_indices.clear()
        app_state.usernames.clear()
        app_state.cookies_dict.clear()
        app_state.cookie_state.current_cookie_idx = 0

    def tearDown(self):
        app_state.cookie_indices[:] = self.original_indices
        app_state.usernames.clear()
        app_state.usernames.update(self.original_usernames)
        app_state.cookies_dict.clear()
        app_state.cookies_dict.update(self.original_cookies)
        app_state.cookie_state.current_cookie_idx = self.original_index


class CredentialStoreReadTests(CredentialStateTestCase):
    def test_missing_index_clears_stale_memory(self):
        app_state.cookie_indices[:] = ["cookies|stale"]
        app_state.usernames["cookies|stale"] = "stale"

        self.assertEqual(CredentialStore(self.keyring).load_index(), [])

        self.assertEqual(app_state.cookie_indices, [])
        self.assertEqual(app_state.usernames, {})
        self.assertEqual(app_state.cookie_state.current_cookie_idx, 0)

    def test_malformed_index_is_preserved_and_reported(self):
        self.keyring.values[(SERVICE, INDEX)] = "not-json"

        with self.assertRaises(CredentialIndexCorruptedError):
            CredentialStore(self.keyring).load_index()

        self.assertEqual(self.keyring.values[(SERVICE, INDEX)], "not-json")

    def test_record_key_must_match_dede_user_id(self):
        self.keyring.put("cookies|1", {"DedeUserID": "2", "SESSDATA": "s"})

        with self.assertRaises(CredentialRecordCorruptedError):
            CredentialStore(self.keyring).read("cookies|1")

    def test_valid_index_reconciles_usernames_without_reordering(self):
        self.keyring.put(INDEX, ["cookies|2", "cookies|1"])
        app_state.usernames.update({"cookies|1": "one", "cookies|stale": "stale"})

        self.assertEqual(
            CredentialStore(self.keyring).load_index(),
            ["cookies|2", "cookies|1"],
        )

        self.assertEqual(app_state.cookie_indices, ["cookies|2", "cookies|1"])
        self.assertEqual(
            app_state.usernames,
            {"cookies|2": "cookies|2", "cookies|1": "one"},
        )

    def test_read_returns_a_copy_of_valid_string_cookie_data(self):
        self.keyring.put("cookies|1", {"DedeUserID": "1", "SESSDATA": "s"})

        record = CredentialStore(self.keyring).read("cookies|1")
        record["SESSDATA"] = "changed"

        self.assertEqual(
            CredentialStore(self.keyring).read("cookies|1"),
            {"DedeUserID": "1", "SESSDATA": "s"},
        )


class CredentialStoreTransactionTests(CredentialStateTestCase):
    def setUp(self):
        super().setUp()
        self.keyring = TransactionKeyring()
        self.store = CredentialStore(self.keyring)

    @staticmethod
    def cookies(uid: str, **extra: str) -> dict[str, str]:
        return {"DedeUserID": uid, "SESSDATA": "session", **extra}

    def seed_accounts(self, *uids: str) -> None:
        for uid in uids:
            self.keyring.put(f"cookies|{uid}", self.cookies(uid))
        self.keyring.put(INDEX, [f"cookies|{uid}" for uid in uids])

    def persisted_index(self) -> list[str]:
        raw = self.keyring.get_password(SERVICE, INDEX)
        return [] if raw is None else loads(raw)

    def remove_at(self, index: int, expected_keys: tuple[str, ...]):
        self.assertTrue(
            hasattr(self.store, "remove_at"),
            "CredentialStore.remove_at is required for atomic UI removal",
        )
        return self.store.remove_at(index, expected_keys)

    def test_remove_at_rejects_negative_index_without_deleting(self):
        self.seed_accounts("1", "2")
        self.store.load_index()
        app_state.cookies_dict.update(self.cookies("1"))
        app_state.cookie_state.current_cookie_idx = -1

        removed = self.remove_at(-1, tuple(app_state.cookie_indices))

        self.assertIsNone(removed)
        self.assertEqual(self.persisted_index(), ["cookies|1", "cookies|2"])
        self.assertIsNotNone(self.keyring.get_password(SERVICE, "cookies|1"))
        self.assertEqual(app_state.cookies_dict, {})
        self.assertEqual(app_state.cookie_state.current_cookie_idx, 2)

    def test_remove_at_rejects_out_of_range_index_without_deleting(self):
        self.seed_accounts("1", "2")
        self.store.load_index()
        app_state.cookies_dict.update(self.cookies("2"))
        app_state.cookie_state.current_cookie_idx = 2

        removed = self.remove_at(2, tuple(app_state.cookie_indices))

        self.assertIsNone(removed)
        self.assertEqual(self.persisted_index(), ["cookies|1", "cookies|2"])
        self.assertIsNotNone(self.keyring.get_password(SERVICE, "cookies|2"))
        self.assertEqual(app_state.cookies_dict, {})
        self.assertEqual(app_state.cookie_state.current_cookie_idx, 2)

    def test_remove_at_missing_index_reconciles_without_deleting_orphan(self):
        self.keyring.put("cookies|1", self.cookies("1"))
        app_state.cookie_indices[:] = ["cookies|1"]
        app_state.usernames["cookies|1"] = "one"
        app_state.cookies_dict.update(self.cookies("1"))
        app_state.cookie_state.current_cookie_idx = 0

        removed = self.remove_at(0, ("cookies|1",))

        self.assertIsNone(removed)
        self.assertIsNotNone(self.keyring.get_password(SERVICE, "cookies|1"))
        self.assertEqual(app_state.cookie_indices, [])
        self.assertEqual(app_state.usernames, {})
        self.assertEqual(app_state.cookies_dict, {})
        self.assertEqual(app_state.cookie_state.current_cookie_idx, 0)

    def test_remove_at_mismatch_reconciles_without_deleting_wrong_account(self):
        self.seed_accounts("1", "2")
        app_state.cookie_indices[:] = ["cookies|2", "cookies|1"]
        app_state.usernames.update(
            {"cookies|2": "two", "cookies|1": "one"}
        )
        app_state.cookies_dict.update(self.cookies("2"))
        app_state.cookie_state.current_cookie_idx = 0

        removed = self.remove_at(
            0, ("cookies|2", "cookies|1")
        )

        self.assertIsNone(removed)
        self.assertEqual(self.persisted_index(), ["cookies|1", "cookies|2"])
        self.assertIsNotNone(self.keyring.get_password(SERVICE, "cookies|1"))
        self.assertIsNotNone(self.keyring.get_password(SERVICE, "cookies|2"))
        self.assertEqual(app_state.cookie_indices, ["cookies|1", "cookies|2"])
        self.assertEqual(app_state.usernames,
                         {"cookies|1": "one", "cookies|2": "two"})
        self.assertEqual(app_state.cookies_dict, {})
        self.assertEqual(app_state.cookie_state.current_cookie_idx, 2)

    def test_remove_at_index_read_failure_preserves_published_state(self):
        self.seed_accounts("1", "2")
        self.store.load_index()
        app_state.usernames.update(
            {"cookies|1": "one", "cookies|2": "two"}
        )
        app_state.cookies_dict.update(self.cookies("2"))
        app_state.cookie_state.current_cookie_idx = 1
        expected_indices = list(app_state.cookie_indices)
        expected_usernames = dict(app_state.usernames)
        expected_cookies = dict(app_state.cookies_dict)
        original_get = self.keyring.get_password

        def fail_index_read(service: str, key: str):
            if key == INDEX:
                raise RuntimeError("index unavailable")
            return original_get(service, key)

        self.keyring.get_password = fail_index_read

        with self.assertRaises(RuntimeError):
            self.remove_at(1, tuple(expected_indices))

        self.assertEqual(app_state.cookie_indices, expected_indices)
        self.assertEqual(app_state.usernames, expected_usernames)
        self.assertEqual(app_state.cookies_dict, expected_cookies)
        self.assertEqual(app_state.cookie_state.current_cookie_idx, 1)
        self.assertEqual(
            loads(self.keyring.values[(SERVICE, INDEX)]), expected_indices
        )
        self.assertIsNotNone(
            self.keyring.values.get((SERVICE, "cookies|2"))
        )

    def test_remove_final_item_returns_committed_empty_collection(self):
        self.seed_accounts("1")

        removed = self.store.remove("cookies|1")

        self.assertEqual(removed.remaining_keys, ())
        self.assertIsNone(self.keyring.get_password(SERVICE, "cookies|1"))
        self.assertEqual(self.persisted_index(), [])

    def test_remove_index_write_failure_restores_secret(self):
        self.seed_accounts("1", "2")
        self.keyring.fail_next("set", INDEX, RuntimeError("index unavailable"))

        with self.assertRaises(CredentialTransactionError):
            self.store.remove("cookies|2")

        self.assertIsNotNone(self.keyring.get_password(SERVICE, "cookies|2"))
        self.assertEqual(self.persisted_index(), ["cookies|1", "cookies|2"])

    def test_migration_deletes_legacy_only_after_new_format_is_committed(self):
        self.keyring.put_raw(LEGACY, dumps(self.cookies("7")))

        self.store.migrate_legacy()

        self.assertEqual(self.keyring.calls[-1], ("delete", LEGACY))
        self.assertEqual(self.persisted_index(), ["cookies|7"])

    def test_new_add_index_failure_deletes_new_secret(self):
        self.seed_accounts("1")
        self.keyring.fail_next("set", INDEX, RuntimeError("index unavailable"))

        with self.assertRaises(CredentialTransactionError):
            self.store.add(self.cookies("2"))

        self.assertIsNone(self.keyring.get_password(SERVICE, "cookies|2"))
        self.assertEqual(self.persisted_index(), ["cookies|1"])

    def test_duplicate_update_failure_restores_previous_value(self):
        self.seed_accounts("1")
        before = self.keyring.get_password(SERVICE, "cookies|1")
        self.keyring.fail_next("set", INDEX, RuntimeError("index unavailable"))

        with self.assertRaises(CredentialTransactionError):
            self.store.add(
                self.cookies("1", SESSDATA="replacement"),
                allow_duplicate=True,
            )

        self.assertEqual(self.keyring.get_password(SERVICE, "cookies|1"), before)

    def test_clear_all_deletes_indexed_and_legacy_keys(self):
        self.seed_accounts("1", "2")
        self.keyring.put_raw(LEGACY, dumps(self.cookies("9")))
        self.keyring.put_raw(KEYRING_ROOM_INFO, "legacy-room")

        self.store.clear_all()

        for key in ("cookies|1", "cookies|2", INDEX, LEGACY,
                    KEYRING_ROOM_INFO):
            self.assertIsNone(self.keyring.get_password(SERVICE, key))

    def test_clear_all_skips_absent_optional_legacy_keys(self):
        self.keyring = TransactionKeyring(reject_missing_deletes=True)
        self.store = CredentialStore(self.keyring)
        self.seed_accounts("1")

        self.store.clear_all()
        self.store.clear_all()

        self.assertIsNone(self.keyring.get_password(SERVICE, "cookies|1"))
        self.assertIsNone(self.keyring.get_password(SERVICE, INDEX))

    def test_add_writes_account_before_index(self):
        stored = self.store.add(self.cookies("2"))

        self.assertEqual(stored.key, "cookies|2")
        self.assertEqual(
            self.keyring.calls,
            [
                ("get", INDEX),
                ("get", "cookies|2"),
                ("set", "cookies|2"),
                ("set", INDEX),
            ],
        )

    def test_remove_deletes_account_before_index(self):
        self.seed_accounts("1")

        removed = self.store.remove("cookies|1")

        self.assertEqual(removed.remaining_keys, ())
        self.assertEqual(
            self.keyring.calls,
            [
                ("get", INDEX),
                ("get", "cookies|1"),
                ("delete", "cookies|1"),
                ("set", INDEX),
            ],
        )

    def test_add_exposes_primary_and_failed_rollback_errors(self):
        index_error = RuntimeError("index unavailable")
        rollback_error = RuntimeError("rollback unavailable")
        self.keyring.fail_next("set", INDEX, index_error)
        self.keyring.fail_next("delete", "cookies|2", rollback_error)

        with self.assertRaises(CredentialTransactionError) as caught:
            self.store.add(self.cookies("2"))

        error = caught.exception
        self.assertIs(error.primary_error, index_error)
        self.assertIs(error.rollback_error, rollback_error)
        self.assertIs(error.__cause__, index_error)
        self.assertEqual(app_state.cookie_indices, [])

    def test_clear_all_failure_restores_previously_deleted_accounts(self):
        self.seed_accounts("1", "2")
        self.keyring.put_raw(LEGACY, dumps(self.cookies("9")))
        delete_error = RuntimeError("legacy unavailable")
        self.keyring.fail_next("delete", LEGACY, delete_error)

        with self.assertRaises(CredentialTransactionError) as caught:
            self.store.clear_all()

        self.assertIs(caught.exception.primary_error, delete_error)
        self.assertIsNotNone(self.keyring.get_password(SERVICE, "cookies|1"))
        self.assertIsNotNone(self.keyring.get_password(SERVICE, "cookies|2"))
        self.assertEqual(self.persisted_index(), ["cookies|1", "cookies|2"])
        self.assertIsNotNone(self.keyring.get_password(SERVICE, LEGACY))

    def test_migration_keeps_legacy_when_account_write_fails(self):
        self.keyring.put_raw(LEGACY, dumps(self.cookies("7")))
        self.keyring.fail_next("set", "cookies|7", RuntimeError("unavailable"))

        with self.assertRaises(CredentialTransactionError):
            self.store.migrate_legacy()

        self.assertIsNotNone(self.keyring.get_password(SERVICE, LEGACY))
        self.assertIsNone(self.keyring.get_password(SERVICE, "cookies|7"))
        self.assertIsNone(self.keyring.get_password(SERVICE, INDEX))

    def test_migration_keeps_legacy_when_index_write_fails(self):
        self.keyring.put_raw(LEGACY, dumps(self.cookies("7")))
        self.keyring.fail_next("set", INDEX, RuntimeError("unavailable"))

        with self.assertRaises(CredentialTransactionError):
            self.store.migrate_legacy()

        self.assertIsNotNone(self.keyring.get_password(SERVICE, LEGACY))
        self.assertIsNone(self.keyring.get_password(SERVICE, "cookies|7"))
        self.assertIsNone(self.keyring.get_password(SERVICE, INDEX))

    def test_compensated_remove_failure_preserves_current_identity_cache(self):
        self.seed_accounts("1", "2")
        app_state.cookie_indices[:] = ["cookies|1", "cookies|2"]
        app_state.usernames.update({"cookies|1": "one", "cookies|2": "two"})
        app_state.cookies_dict.update(self.cookies("2"))
        app_state.cookie_state.current_cookie_idx = 1
        self.keyring.fail_next("set", INDEX, RuntimeError("unavailable"))

        with self.assertRaises(CredentialTransactionError):
            self.store.remove("cookies|2")

        self.assertEqual(app_state.cookie_indices, ["cookies|1", "cookies|2"])
        self.assertEqual(app_state.usernames, {"cookies|1": "one", "cookies|2": "two"})
        self.assertEqual(app_state.cookies_dict, self.cookies("2"))
        self.assertEqual(app_state.cookie_state.current_cookie_idx, 1)

    def test_add_account_write_failure_is_a_transaction_error(self):
        self.keyring.fail_next("set", "cookies|1", RuntimeError("unavailable"))

        with self.assertRaises(CredentialTransactionError):
            self.store.add(self.cookies("1"))

        self.assertEqual(app_state.cookie_indices, [])
        self.assertEqual(self.persisted_index(), [])

    def test_remove_secret_delete_failure_is_a_transaction_error(self):
        self.seed_accounts("1")
        app_state.cookie_indices[:] = ["cookies|stale"]
        app_state.usernames["cookies|stale"] = "stale"
        self.keyring.fail_next("delete", "cookies|1", RuntimeError("unavailable"))

        with self.assertRaises(CredentialTransactionError):
            self.store.remove("cookies|1")

        self.assertEqual(self.persisted_index(), ["cookies|1"])
        self.assertEqual(app_state.cookie_indices, ["cookies|stale"])
        self.assertEqual(app_state.usernames, {"cookies|stale": "stale"})
