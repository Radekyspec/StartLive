import unittest

from src.core import app_state
from src.core.constant import (
    KEYRING_COOKIES,
    KEYRING_COOKIES_INDEX,
    KEYRING_SERVICE_NAME,
)
from src.core.credentials.store import (
    CredentialIndexCorruptedError,
    CredentialRecordCorruptedError,
    CredentialStore,
)
from tests.helpers import FakeKeyring


SERVICE = KEYRING_SERVICE_NAME
INDEX = KEYRING_COOKIES_INDEX
LEGACY = KEYRING_COOKIES


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
