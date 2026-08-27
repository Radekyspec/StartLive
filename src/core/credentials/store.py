from json import loads
from typing import Any

import keyring

from src.core import app_state
from src.core.constant import KEYRING_COOKIES_INDEX, KEYRING_SERVICE_NAME


class CredentialIndexCorruptedError(Exception):
    """Raised when the persisted credential index cannot be safely used."""


class CredentialRecordCorruptedError(Exception):
    """Raised when a persisted credential record cannot be safely used."""

    def __init__(self, key: str, reason: str):
        super().__init__(f"{key}: {reason}")


class CredentialStore:
    def __init__(self, backend: Any = keyring):
        self._backend = backend

    def load_index(self) -> list[str]:
        raw = self._backend.get_password(
            KEYRING_SERVICE_NAME, KEYRING_COOKIES_INDEX
        )
        if raw is None:
            return self._commit_index([])
        try:
            keys = loads(raw)
        except (TypeError, ValueError) as exc:
            self._clear_unusable_cache()
            raise CredentialIndexCorruptedError("cookiesIndex is not JSON") from exc
        if (
            not isinstance(keys, list)
            or any(
                not isinstance(key, str) or not key.startswith("cookies|")
                for key in keys
            )
            or len(keys) != len(set(keys))
        ):
            self._clear_unusable_cache()
            raise CredentialIndexCorruptedError("cookiesIndex has invalid entries")
        return self._commit_index(keys)

    def read(self, key: str) -> dict[str, str]:
        raw = self._backend.get_password(KEYRING_SERVICE_NAME, key)
        if raw is None:
            raise CredentialRecordCorruptedError(key, "credential is missing")
        try:
            record = loads(raw)
        except (TypeError, ValueError) as exc:
            raise CredentialRecordCorruptedError(
                key, "credential is not JSON"
            ) from exc
        if not isinstance(record, dict):
            raise CredentialRecordCorruptedError(key, "credential is not a mapping")
        uid = record.get("DedeUserID")
        if not isinstance(uid, str) or not uid or key != f"cookies|{uid}":
            raise CredentialRecordCorruptedError(
                key, "credential identity does not match its key"
            )
        if any(
            not isinstance(name, str) or not isinstance(value, str)
            for name, value in record.items()
        ):
            raise CredentialRecordCorruptedError(
                key, "credential contains non-string cookie data"
            )
        return dict(record)

    @staticmethod
    def _clear_unusable_cache() -> None:
        app_state.cookie_indices.clear()
        app_state.usernames.clear()
        app_state.cookies_dict.clear()
        app_state.cookie_state.current_cookie_idx = 0

    @staticmethod
    def _commit_index(keys: list[str]) -> list[str]:
        previous_usernames = dict(app_state.usernames)
        app_state.cookie_indices[:] = keys
        app_state.usernames.clear()
        app_state.usernames.update(
            {key: previous_usernames.get(key, key) for key in keys}
        )
        if not keys:
            app_state.cookie_state.current_cookie_idx = 0
        return app_state.cookie_indices
