from json import loads
from enum import Enum
from typing import Any, Callable, Mapping

# package import
from keyring import get_password, delete_password
from requests import RequestException
from requests.cookies import cookiejar_from_dict

# local package import
from src.core import app_state
from src.core.constant import *
from src.core.constant import HeadersType
from src.core.credentials import (
    CredentialRecordCorruptedError,
    CredentialStore,
    CredentialTransactionError,
)
from src.core.log import get_logger
from src.core.sign import livehime_sign
from src.core.workers.base import BaseWorker, Presenter


AUTH_INVALID_CODES = frozenset({-101})
NAV_URL = "https://api.bilibili.com/x/web-interface/nav"


class CredentialValidationError(Exception):
    """Raised when credential validation should be retried later."""


class ValidationOutcome(Enum):
    VALID = ("valid", "credential is valid")
    PERMANENT_INVALID = ("permanent_invalid", "credential is invalid")
    TEMPORARY_FAILURE = ("temporary_failure", "credential validation failed")

    def __init__(self, label: str, message: str):
        self.label = label
        self.message = message


class CredentialManagerWorker(BaseWorker):
    def __init__(self, presenter: Presenter, /, cookie_index: int,
                 is_new: bool = False):
        super().__init__(name="凭据管理", headers_type=HeadersType.WEB,
                         inherit_account_cookies=False, presenter=presenter)
        self.cookie_index = cookie_index
        self.is_new = is_new
        self._store = CredentialStore()
        self.logger = get_logger(self.__class__.__name__)

    @staticmethod
    def get_cookie_indices() -> list[str]:
        return CredentialStore().load_index()

    @staticmethod
    def reset_default():
        app_state.room_info_default()
        app_state.scan_settings_default()
        app_state.stream_status_default()

    @staticmethod
    def add_cookie(allow_duplicate: bool = False) -> str:
        """
        Adds a new cookie credential to the credential manager.

        This static method adds a unique cookie credential to the credential manager,
        using the combination of a user ID and the application configuration dictionary.
        If the cookie credential already exists, a duplicate error is raised.
        The credential is stored securely alongside the index of cookie credentials.

        :raises CredentialDuplicatedError: If the cookie credential already exists in
            the credential manager.
        :return: The unique key for the added cookie credential.
        :rtype: str
        """
        return CredentialStore().add(
            app_state.cookies_dict,
            allow_duplicate=allow_duplicate,
        ).key

    def _request_nav(self) -> Mapping[str, Any]:
        try:
            response = self._session.get(
                NAV_URL,
                params=livehime_sign(
                    {}, access_key=False, build=False, version=False
                ),
            )
            response.raise_for_status()
            response.encoding = "utf-8"
            payload = response.json()
        except (RequestException, ValueError) as error:
            raise CredentialValidationError(
                "credential validation request failed"
            ) from error
        if not isinstance(payload, Mapping):
            raise CredentialValidationError(
                "credential validation response is malformed"
            )
        return payload

    def _classify_nav(
        self, payload: Mapping[str, Any], expected_uid: str
    ) -> ValidationOutcome:
        code = payload.get("code")
        if isinstance(code, bool) or not isinstance(code, int):
            outcome = ValidationOutcome.TEMPORARY_FAILURE
            log_code: int | str = "invalid"
        elif code in AUTH_INVALID_CODES:
            outcome = ValidationOutcome.PERMANENT_INVALID
            log_code = code
        elif code != 0:
            outcome = ValidationOutcome.TEMPORARY_FAILURE
            log_code = code
        else:
            log_code = code
            data = payload.get("data")
            if not isinstance(data, Mapping):
                outcome = ValidationOutcome.TEMPORARY_FAILURE
            elif data.get("isLogin") is False:
                outcome = ValidationOutcome.PERMANENT_INVALID
            elif data.get("isLogin") is not True:
                outcome = ValidationOutcome.TEMPORARY_FAILURE
            else:
                mid = data.get("mid")
                uname = data.get("uname")
                if (
                    isinstance(mid, bool)
                    or not isinstance(mid, (int, str))
                    or not str(mid)
                    or not isinstance(uname, str)
                ):
                    outcome = ValidationOutcome.TEMPORARY_FAILURE
                elif str(mid) != expected_uid:
                    outcome = ValidationOutcome.PERMANENT_INVALID
                else:
                    outcome = ValidationOutcome.VALID
        self.logger.info(
            "credential validation code=%s classification=%s",
            log_code,
            outcome.label,
        )
        return outcome

    @staticmethod
    def _validation_store_error(error: Exception) -> CredentialValidationError:
        return CredentialValidationError("credential store is unavailable")

    def _remove_invalid(self, key: str) -> list[str]:
        try:
            return list(self._store.remove(key).remaining_keys)
        except CredentialTransactionError:
            raise
        except Exception as error:
            raise self._validation_store_error(error) from error

    def run(self, report_progress: Callable | None, *args, **kwargs):

        if app_state.obs_settings:
            self.logger.info("using existing obs settings")
        elif (saved_settings := get_password(KEYRING_SERVICE_NAME,
                                             KEYRING_SETTINGS)) is not None:
            app_state.obs_settings.update(loads(saved_settings))
            self.logger.info("stored obs settings loaded")
        else:
            app_state.obs_settings_default()
            self.logger.info(f"obs_default_settings loaded")
        if get_password(KEYRING_SERVICE_NAME,
                        KEYRING_ROOM_INFO) is not None:
            delete_password(KEYRING_SERVICE_NAME, KEYRING_ROOM_INFO)
        app_state.room_info_default()
        self.logger.info(f"room_default_settings loaded")

        if self.is_new:
            app_state.scan_status["is_new"] = True
            self.logger.info(f"new credentials created, exiting")
            app_state.cookies_dict.clear()
            return self.cookie_index

        try:
            self._store.migrate_legacy()
            keys = self._store.load_index()
        except CredentialTransactionError:
            raise
        except Exception as error:
            raise self._validation_store_error(error) from error

        candidate = self.cookie_index
        app_state.cookie_state.current_cookie_idx = len(keys)
        baseline = self._session.cookies.copy()
        while keys:
            candidate = min(max(candidate, 0), len(keys) - 1)
            key = keys[candidate]
            try:
                cookies = self._store.read(key)
            except CredentialRecordCorruptedError:
                keys = self._remove_invalid(key)
                continue
            except Exception as error:
                raise self._validation_store_error(error) from error

            self._session.cookies.clear()
            self._session.cookies.update(baseline)
            cookiejar_from_dict(
                cookies, cookiejar=self._session.cookies, overwrite=True
            )
            payload = self._request_nav()
            outcome = self._classify_nav(payload, cookies["DedeUserID"])
            if outcome is ValidationOutcome.PERMANENT_INVALID:
                keys = self._remove_invalid(key)
                continue
            if outcome is not ValidationOutcome.VALID:
                raise CredentialValidationError(outcome.message)

            data = payload["data"]
            app_state.usernames[key] = USERNAME_DISPLAY_TEMPLATE.format(
                data["uname"], data["mid"]
            )
            app_state.cookies_dict.clear()
            app_state.cookies_dict.update(cookies)
            app_state.cookie_state.current_cookie_idx = candidate
            app_state.scan_status["scanned"] = True
            return candidate

        app_state.cookies_dict.clear()
        app_state.cookie_state.current_cookie_idx = 0
        app_state.scan_status["is_new"] = True
        return 0
