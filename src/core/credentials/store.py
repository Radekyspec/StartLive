from dataclasses import dataclass
from json import dumps, loads
import logging
from typing import Any, Mapping

import keyring

from src.core import app_state
from src.core.constant import (
    KEYRING_COOKIES,
    KEYRING_COOKIES_INDEX,
    KEYRING_ROOM_INFO,
    KEYRING_SERVICE_NAME,
)
from src.core.exceptions import CredentialDuplicatedError


class CredentialIndexCorruptedError(Exception):
    """Raised when the persisted credential index cannot be safely used."""


class CredentialRecordCorruptedError(Exception):
    """Raised when a persisted credential record cannot be safely used."""

    def __init__(self, key: str, reason: str):
        super().__init__(f"{key}: {reason}")


class CredentialTransactionError(Exception):
    """Raised when a credential write cannot be durably completed."""

    def __init__(
        self,
        operation: str,
        primary_error: Exception,
        rollback_error: Exception | None = None,
    ):
        super().__init__(f"{operation} credential transaction failed")
        self.operation = operation
        self.primary_error = primary_error
        self.rollback_error = rollback_error
        # Short aliases keep callers from having to inspect exception details.
        self.primary = primary_error
        self.rollback = rollback_error


@dataclass(frozen=True)
class StoredCredential:
    key: str
    index: int


@dataclass(frozen=True)
class RemovedCredential:
    key: str
    uid: str
    former_index: int
    remaining_keys: tuple[str, ...]


class CredentialStore:
    def __init__(self, backend: Any = keyring):
        self._backend = backend
        self._logger = logging.getLogger(__name__)

    def load_index(self) -> list[str]:
        raw = self._backend.get_password(
            KEYRING_SERVICE_NAME, KEYRING_COOKIES_INDEX
        )
        return self._decode_index(raw, commit=True)

    def read(self, key: str) -> dict[str, str]:
        raw = self._backend.get_password(KEYRING_SERVICE_NAME, key)
        if raw is None:
            raise CredentialRecordCorruptedError(key, "credential is missing")
        return self._decode_record(key, raw)

    def add(self, cookies: Mapping[str, str], *,
            allow_duplicate: bool = False) -> StoredCredential:
        key = self._key_for_cookies(cookies)
        keys = self._load_index_for_transaction()
        old_raw = self._backend.get_password(KEYRING_SERVICE_NAME, key)
        if key in keys and not allow_duplicate:
            raise CredentialDuplicatedError(key)

        new_keys = keys if key in keys else [*keys, key]
        try:
            self._backend.set_password(
                KEYRING_SERVICE_NAME, key, dumps(dict(cookies))
            )
        except Exception as primary:
            raise CredentialTransactionError("add", primary) from primary
        try:
            self._backend.set_password(
                KEYRING_SERVICE_NAME, KEYRING_COOKIES_INDEX, dumps(new_keys)
            )
        except Exception as primary:
            rollback = self._restore_replaced_value(key, old_raw)
            raise CredentialTransactionError("add", primary, rollback) from primary

        self._commit_index(new_keys)
        return StoredCredential(key=key, index=new_keys.index(key))

    def remove(self, key: str) -> RemovedCredential:
        keys = self._load_index_for_transaction()
        former_index = keys.index(key)
        old_raw = self._backend.get_password(KEYRING_SERVICE_NAME, key)
        try:
            if old_raw is not None:
                self._backend.delete_password(KEYRING_SERVICE_NAME, key)
        except Exception as primary:
            raise CredentialTransactionError("remove", primary) from primary

        new_keys = keys[:former_index] + keys[former_index + 1:]
        try:
            self._backend.set_password(
                KEYRING_SERVICE_NAME, KEYRING_COOKIES_INDEX, dumps(new_keys)
            )
        except Exception as primary:
            rollback = self._restore_deleted_value(key, old_raw)
            raise CredentialTransactionError("remove", primary, rollback) from primary

        self._commit_index(new_keys)
        self._cleanup_removed_identity(key, former_index)
        return RemovedCredential(
            key, self._uid_from_key(key), former_index, tuple(new_keys)
        )

    def migrate_legacy(self) -> None:
        legacy = self._backend.get_password(KEYRING_SERVICE_NAME, KEYRING_COOKIES)
        index = self._backend.get_password(
            KEYRING_SERVICE_NAME, KEYRING_COOKIES_INDEX
        )
        if legacy is None or index is not None:
            return
        cookies = self._decode_record(KEYRING_COOKIES, legacy, legacy=True)
        stored = self.add(cookies)
        try:
            self._backend.delete_password(KEYRING_SERVICE_NAME, KEYRING_COOKIES)
        except Exception:
            self._logger.warning(
                "Legacy credential cleanup failed after %s was committed",
                stored.key,
            )

    def clear_all(self) -> None:
        keys = self._load_index_for_transaction()
        deleted: list[tuple[str, str | None]] = []
        targets = [*keys, KEYRING_COOKIES, KEYRING_ROOM_INFO, KEYRING_COOKIES_INDEX]
        try:
            for key in targets:
                raw = self._backend.get_password(KEYRING_SERVICE_NAME, key)
                self._backend.delete_password(KEYRING_SERVICE_NAME, key)
                deleted.append((key, raw))
        except Exception as primary:
            rollback = self._restore_deleted_values(deleted)
            raise CredentialTransactionError("clear_all", primary, rollback) from primary

        self._clear_unusable_cache()

    def _load_index_for_transaction(self) -> list[str]:
        raw = self._backend.get_password(
            KEYRING_SERVICE_NAME, KEYRING_COOKIES_INDEX
        )
        return self._decode_index(raw, commit=False)

    def _decode_index(self, raw: str | None, *, commit: bool) -> list[str]:
        if raw is None:
            return self._commit_index([]) if commit else []
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
        return self._commit_index(keys) if commit else keys

    @staticmethod
    def _decode_record(
        key: str, raw: str, *, legacy: bool = False
    ) -> dict[str, str]:
        try:
            record = loads(raw)
        except (TypeError, ValueError) as exc:
            raise CredentialRecordCorruptedError(
                key, "credential is not JSON"
            ) from exc
        if not isinstance(record, dict):
            raise CredentialRecordCorruptedError(key, "credential is not a mapping")
        uid = record.get("DedeUserID")
        if (
            not isinstance(uid, str)
            or not uid
            or (not legacy and key != f"cookies|{uid}")
        ):
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
    def _key_for_cookies(cookies: Mapping[str, str]) -> str:
        uid = cookies.get("DedeUserID")
        if not isinstance(uid, str) or not uid:
            raise ValueError("cookies must contain a non-empty string DedeUserID")
        if any(
            not isinstance(name, str) or not isinstance(value, str)
            for name, value in cookies.items()
        ):
            raise ValueError("cookies must contain only string data")
        return f"cookies|{uid}"

    @staticmethod
    def _uid_from_key(key: str) -> str:
        return key.removeprefix("cookies|")

    def _restore_replaced_value(
        self, key: str, old_raw: str | None
    ) -> Exception | None:
        try:
            if old_raw is None:
                self._backend.delete_password(KEYRING_SERVICE_NAME, key)
            else:
                self._backend.set_password(KEYRING_SERVICE_NAME, key, old_raw)
        except Exception as rollback:
            return rollback
        return None

    def _restore_deleted_value(
        self, key: str, old_raw: str | None
    ) -> Exception | None:
        if old_raw is None:
            return None
        try:
            self._backend.set_password(KEYRING_SERVICE_NAME, key, old_raw)
        except Exception as rollback:
            return rollback
        return None

    def _restore_deleted_values(
        self, deleted: list[tuple[str, str | None]]
    ) -> Exception | None:
        rollback_error = None
        for key, raw in reversed(deleted):
            if raw is None:
                continue
            try:
                self._backend.set_password(KEYRING_SERVICE_NAME, key, raw)
            except Exception as rollback:
                if rollback_error is None:
                    rollback_error = rollback
        return rollback_error

    @staticmethod
    def _clear_unusable_cache() -> None:
        app_state.cookie_indices.clear()
        app_state.usernames.clear()
        app_state.cookies_dict.clear()
        app_state.cookie_state.current_cookie_idx = 0

    @staticmethod
    def _cleanup_removed_identity(key: str, former_index: int) -> None:
        uid = CredentialStore._uid_from_key(key)
        app_state.usernames.pop(key, None)
        if app_state.cookies_dict.get("DedeUserID") == uid:
            app_state.cookies_dict.clear()
        if not app_state.cookie_indices:
            app_state.cookie_state.current_cookie_idx = 0
        elif former_index < app_state.cookie_state.current_cookie_idx:
            app_state.cookie_state.current_cookie_idx -= 1
        elif app_state.cookie_state.current_cookie_idx >= len(
            app_state.cookie_indices
        ):
            app_state.cookie_state.current_cookie_idx = len(
                app_state.cookie_indices
            ) - 1

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
