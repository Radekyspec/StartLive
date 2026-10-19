from typing import Any, Callable, Mapping

# package import
from requests import RequestException
from requests.cookies import cookiejar_from_dict

# local package import
from startlive.core import app_state
from startlive.core.constant import *
from startlive.core.constant import HeadersType
from startlive.core.credentials import CredentialStore
from startlive.core.credentials.backend import get_password, delete_password
from startlive.core.exceptions import (
    CredentialRecordCorruptedError,
    CredentialTransactionError,
    CredentialValidationError,
    TaskCancelled
)
from startlive.core.log import get_logger
from startlive.core.sign import livehime_sign
from startlive.core.workers.base import BaseWorker, Presenter


class CredentialManagerWorker(BaseWorker):
    def __init__(self, presenter: Presenter, /, cookie_index: int,
                 is_new: bool = False):
        super().__init__(name="凭据管理", headers_type=HeadersType.WEB,
                         inherit_account_cookies=False, presenter=presenter)
        self._account_generation, _ = app_state.capture_account_context()
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

    def _request_nav(self) -> Mapping[str, Any]:
        try:
            response = self._session.get(
                "https://api.bilibili.com/x/web-interface/nav",
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
        elif code == -101:
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
            elif not data.get("isLogin"):
                outcome = ValidationOutcome.PERMANENT_INVALID
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
            outcome,
        )
        return outcome

    def _remove_invalid(self, key: str) -> list[str]:
        try:
            with app_state.account_guard(self._account_generation):
                remaining = list(self._store.remove(key).remaining_keys)
                # Removing the active invalid record can itself retire the account.
                self._account_generation, _ = app_state.capture_account_context()
                return remaining
        except (CredentialTransactionError, TaskCancelled):
            raise
        except Exception as error:
            raise CredentialValidationError(
                "credential store is unavailable") from error

    def run(self, report_progress: Callable | None, *args, **kwargs):

        # Global OBS settings are loaded by app_state, independently of login.
        if get_password(KEYRING_SERVICE_NAME,
                        KEYRING_ROOM_INFO) is not None:
            delete_password(KEYRING_SERVICE_NAME, KEYRING_ROOM_INFO)
        with app_state.account_guard(self._account_generation):
            app_state.room_info_default()
        self.logger.info(f"room_default_settings loaded")

        if self.is_new:
            with app_state.account_guard(self._account_generation):
                app_state.scan_status["is_new"] = True
                app_state.replace_account_cookies({})
            self.logger.info("new credentials created, exiting")
            return self.cookie_index

        try:
            with app_state.account_guard(self._account_generation):
                self._store.migrate_legacy()
                keys = self._store.load_index()
        except (CredentialTransactionError, TaskCancelled):
            raise
        except Exception as error:
            raise CredentialValidationError(
                "credential store is unavailable") from error

        candidate = self.cookie_index
        with app_state.account_guard(self._account_generation):
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
                raise CredentialValidationError(
                    "credential store is unavailable") from error

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
                raise CredentialValidationError("credential validation failed")

            with app_state.account_guard(self._account_generation):
                data = payload["data"]
                app_state.usernames[key] = USERNAME_DISPLAY_TEMPLATE.format(
                    data["uname"], data["mid"]
                )
                app_state.replace_account_cookies(cookies)
                app_state.cookie_state.current_cookie_idx = candidate
                app_state.scan_status["scanned"] = True
            return candidate

        with app_state.account_guard(self._account_generation):
            app_state.replace_account_cookies({})
            app_state.cookie_state.current_cookie_idx = 0
            app_state.scan_status["is_new"] = True
        return 0
