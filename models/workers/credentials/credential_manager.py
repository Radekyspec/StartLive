from json import loads

from PySide6.QtCore import Slot
# package import
from keyring import get_password, set_password, delete_password
from requests.cookies import cookiejar_from_dict

# local package import
import app_state
import constant
from app_state import dumps
from constant import *
from exceptions import CredentialExpiredError, CredentialDuplicatedError
from models.log import get_logger
from models.states import LoginState
from models.workers.base import BaseWorker, run_wrapper
from models.workers.login.fetch_login import FetchLoginWorker
from models.workers.usernames.fetch_usernames import FetchUsernamesWorker
from sign import livehime_sign


class CredentialManagerWorker(BaseWorker):
    def __init__(self, cookie_index: int, is_new: bool = False):
        super().__init__(name="凭据管理")
        self.cookie_index = cookie_index
        self.is_new = is_new
        self.logger = get_logger(self.__class__.__name__)

    @staticmethod
    def get_cookie_indices() -> list[str]:
        if (cookies_index := get_password(KEYRING_SERVICE_NAME,
                                          KEYRING_COOKIES_INDEX)) is not None:
            cookies_index = loads(cookies_index)
            if not isinstance(cookies_index, list):
                return []
            # valid, update cache
            app_state.cookie_indices.clear()
            app_state.cookie_indices.extend(cookies_index)
            return app_state.cookie_indices
        return []

    @staticmethod
    def reset_default():
        app_state.room_info_default()
        app_state.scan_settings_default()
        app_state.stream_status_default()

    @staticmethod
    def add_cookie():
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
        uid = app_state.cookies_dict["DedeUserID"]
        cookie_key = f"cookies|{uid}"
        CredentialManagerWorker.get_cookie_indices()
        if cookie_key in app_state.cookie_indices:
            raise CredentialDuplicatedError(cookie_key)
        app_state.cookie_indices.append(cookie_key)
        app_state.usernames[cookie_key] = cookie_key
        set_password(KEYRING_SERVICE_NAME, cookie_key,
                     dumps(app_state.cookies_dict))
        set_password(KEYRING_SERVICE_NAME, KEYRING_COOKIES_INDEX,
                     dumps(app_state.cookie_indices))
        return cookie_key

    @Slot()
    @run_wrapper
    def run(self, /) -> None:
        if app_state.obs_settings.internal:
            self.logger.info(
                f"use existing obs settings: {app_state.obs_settings.internal}")
        elif (saved_settings := get_password(KEYRING_SERVICE_NAME,
                                             KEYRING_SETTINGS)) is not None:
            app_state.obs_settings.update(loads(saved_settings))
            self.logger.info(f"obs_settings loaded: {saved_settings}")
        else:
            app_state.obs_settings_default()
            self.logger.info(f"obs_default_settings loaded")
        if get_password(KEYRING_SERVICE_NAME, KEYRING_ROOM_INFO) is not None:
            delete_password(KEYRING_SERVICE_NAME, KEYRING_ROOM_INFO)
        app_state.room_info_default()
        self.logger.info(f"room_default_settings loaded")

        if self.is_new:
            self.logger.info(f"new credentials created, exiting")
            app_state.cookies_dict.clear()
            return

        # Old version cookie storage, change to index
        if (saved_cookies := get_password(KEYRING_SERVICE_NAME,
                                          KEYRING_COOKIES)) is not None and \
                get_password(KEYRING_SERVICE_NAME,
                             KEYRING_COOKIES_INDEX) is None:
            saved_cookies = loads(saved_cookies)
            uid = saved_cookies["DedeUserID"]
            delete_password(KEYRING_SERVICE_NAME, KEYRING_COOKIES)
            set_password(KEYRING_SERVICE_NAME, KEYRING_COOKIES_INDEX,
                         dumps([f"cookies|{uid}"]))
            set_password(KEYRING_SERVICE_NAME, f"cookies|{uid}",
                         dumps(saved_cookies))
            self.logger.info(f"cookies index created")

        self.get_cookie_indices()
        self.logger.info(f"cookies index loaded: {app_state.cookie_indices}")
        app_state.usernames.clear()
        app_state.usernames.update({i: i for i in app_state.cookie_indices})
        if not app_state.cookie_indices or (
                saved_cookies := get_password(
                    KEYRING_SERVICE_NAME,
                    app_state.cookie_indices[
                        self.cookie_index])) is None:
            self.is_new = True
            return
        saved_cookies = loads(saved_cookies)
        cookiejar_from_dict(saved_cookies,
                            cookiejar=self._session.cookies)
        self._session.headers.update(constant.HEADERS_WEB)
        nav_url = "https://api.bilibili.com/x/web-interface/nav"
        self.logger.info(f"nav Request")
        response = self._session.get(
            nav_url,
            params=livehime_sign({},
                                 access_key=False,
                                 build=False,
                                 version=False))
        response.encoding = "utf-8"
        self.logger.info("nav Response")
        response = response.json()
        if response["code"] != 0:
            app_state.scan_status["expired"] = True
            raise CredentialExpiredError("登录凭据过期, 请重新登录")
        if (current_username := app_state.cookie_indices[
            self.cookie_index]) in app_state.usernames:
            app_state.usernames[
                current_username] = USERNAME_DISPLAY_TEMPLATE.format(
                response["data"]["uname"],
                response["data"]["mid"]
            )
        app_state.cookies_dict.clear()
        app_state.cookies_dict.update(saved_cookies)
        app_state.scan_status["scanned"] = True

    @Slot()
    def on_finished(self, parent_window: "MainWindow", state: LoginState):
        FetchLoginWorker.post_login(parent_window, state)
        if not self.is_new:
            fetch_usernames = FetchUsernamesWorker(
                app_state.cookie_indices[self.cookie_index])
            parent_window.add_thread(
                fetch_usernames,
                on_finished=fetch_usernames.on_finished,
            )
        else:
            app_state.scan_status["is_new"] = True
        state.credentialLoaded.emit()
        panel = parent_window.panel
        panel.host_input.setText(
            app_state.obs_settings.get("ip_addr", "localhost"))
        panel.port_input.setText(app_state.obs_settings.get("port", "4455"))
        panel.pass_input.setText(app_state.obs_settings.get("password", ""))
        panel.obs_auto_live_checkbox.setChecked(
            app_state.obs_settings.get("auto_live", False))
        panel.obs_auto_connect_checkbox.setChecked(
            app_state.obs_settings.get("auto_connect", False))
        self._session.close()
