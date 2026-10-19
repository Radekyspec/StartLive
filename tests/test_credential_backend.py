import unittest
from unittest.mock import patch

from keyring.backends.fail import Keyring as UnavailableKeyring
from keyring.backends.null import Keyring as DisabledKeyring
from keyring.errors import NoKeyringError, PasswordDeleteError

from startlive.core.credentials import backend
from tests.helpers import FakeKeyring


class CredentialBackendTests(unittest.TestCase):
    def setUp(self):
        self.backend_patch = patch.object(backend, "_backend", None)
        self.backend_patch.start()
        self.addCleanup(self.backend_patch.stop)
        self.platform_patch = patch.object(backend, "system", return_value="Linux")
        self.platform_patch.start()
        self.addCleanup(self.platform_patch.stop)

    def test_unavailable_and_disabled_linux_backends_keep_session_credentials(self):
        for selected in (UnavailableKeyring(), DisabledKeyring()):
            with self.subTest(selected=type(selected).__module__), \
                    patch.object(backend, "_backend", None), \
                    patch.object(backend.keyring, "get_keyring", return_value=selected):
                self.assertIsNone(backend.get_password("fixture", "account"))
                backend.set_password("fixture", "account", "synthetic-secret")
                self.assertEqual(backend.get_password("fixture", "account"),
                                 "synthetic-secret")
                self.assertTrue(backend.using_session_keyring())
                backend.delete_password("fixture", "account")
                self.assertIsNone(backend.get_password("fixture", "account"))
                with self.assertRaises(PasswordDeleteError):
                    backend.delete_password("fixture", "account")

    def test_session_mode_does_not_replace_the_global_keyring(self):
        with patch.object(backend.keyring, "get_keyring",
                          return_value=UnavailableKeyring()), \
                patch.object(backend.keyring, "set_keyring") as replace:
            backend.set_password("fixture", "account", "synthetic-secret")
        replace.assert_not_called()

    def test_later_persistent_backend_failures_are_not_hidden(self):
        selected = FakeKeyring()
        with patch.object(backend.keyring, "get_keyring", return_value=selected):
            backend.set_password("fixture", "account", "original")
            selected.failures["set", "account"] = RuntimeError("offline")
            with self.assertRaisesRegex(RuntimeError, "offline"):
                backend.set_password("fixture", "account", "replacement")
            self.assertEqual(backend.get_password("fixture", "account"), "original")
        self.assertFalse(backend.using_session_keyring())

    def test_non_linux_missing_backends_keep_their_existing_error(self):
        for platform in ("Windows", "Darwin"):
            with self.subTest(platform=platform), \
                    patch.object(backend, "_backend", None), \
                    patch.object(backend, "system", return_value=platform), \
                    patch.object(backend.keyring, "get_keyring",
                                 return_value=UnavailableKeyring()):
                with self.assertRaises(NoKeyringError):
                    backend.get_password("fixture", "account")
                self.assertFalse(backend.using_session_keyring())

    def test_reporting_storage_mode_does_not_initialize_the_keyring(self):
        with patch.object(backend.keyring, "get_keyring") as select:
            self.assertFalse(backend.using_session_keyring())
        select.assert_not_called()

    def test_a_new_session_does_not_recover_temporary_credentials(self):
        with patch.object(backend.keyring, "get_keyring",
                          return_value=UnavailableKeyring()):
            backend.set_password("fixture", "account", "synthetic-secret")
            with patch.object(backend, "_backend", None):
                self.assertIsNone(backend.get_password("fixture", "account"))
