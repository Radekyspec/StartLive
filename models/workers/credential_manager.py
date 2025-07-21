from json import loads

from PySide6.QtCore import Slot
# package import
from keyring import get_password, set_password, delete_password
from requests.cookies import cookiejar_from_dict

# local package import
import config
import constant
from config import dumps
from constant import *
from exceptions import CredentialExpiredError, CredentialDuplicatedError
from models.log import get_logger
from models.workers.base import BaseWorker, run_wrapper
from sign import livehime_sign
from .fetch_login import FetchLoginWorker


class CredentialManagerWorker(BaseWorker):
    def __init__(self, cookie_index: int, is_new: bool = False):
        super().__init__(name="凭据管理")
        self.cookie_index = cookie_index
        self.is_new = is_new
        self.logger = get_logger(self.__class__.__name__)

    @staticmethod
    def obs_settings_default():
        config.obs_settings.update({
            "ip_addr": "localhost",
            "port": "4455",
            "password": "",
            "auto_live": False,
            "auto_connect": False
        })

    @staticmethod
    def get_cookies_index() -> list[str]:
        if (cookies_index := get_password(KEYRING_SERVICE_NAME,
                                          KEYRING_COOKIES_INDEX)) is not None:
            cookies_index = loads(cookies_index)
            return cookies_index
        return []

    @staticmethod
    def _room_info_default():
        config.room_info.update({
            "room_id": "",
            "title": "",
            "parent_area": "",
            "area": "",
            "announcement": "",
        })

    @staticmethod
    def _scan_settings_default():
        config.scan_status.update({
            "scanned": False, "qr_key": None, "qr_url": None,
            "timeout": False, "wait_for_confirm": False,
            "area_updated": False, "room_updated": False,
            "const_updated": True, "announce_updated": False
        })

    @staticmethod
    def _stream_status_default():
        config.stream_status.update({
            "live_status": False,
            "required_face": False,
            "identified_face": False,
            "face_url": None,
            "stream_addr": None,
            "stream_key": None
        })

    @staticmethod
    def reset_default():
        CredentialManagerWorker._room_info_default()
        CredentialManagerWorker._scan_settings_default()
        CredentialManagerWorker._stream_status_default()

    @staticmethod
    def add_cookie():
        """
        Adding cookie from config.cookies_dict to keyring
        :return:
        """
        uid = config.cookies_dict["DedeUserID"]
        cookie_key = f"cookies|{uid}"
        cookies_index = CredentialManagerWorker.get_cookies_index()
        if cookie_key in cookies_index:
            raise CredentialDuplicatedError(cookie_key)
        cookies_index.append(cookie_key)
        set_password(KEYRING_SERVICE_NAME, cookie_key,
                     dumps(config.cookies_dict))
        set_password(KEYRING_SERVICE_NAME, KEYRING_COOKIES_INDEX,
                     dumps(cookies_index))

    @Slot()
    @run_wrapper
    def run(self, /) -> None:
        if config.obs_settings.internal:
            self.logger.info(
                f"use existing obs settings: {config.obs_settings.internal}")
        elif (saved_settings := get_password(KEYRING_SERVICE_NAME,
                                             KEYRING_SETTINGS)) is not None:
            config.obs_settings.update(loads(saved_settings))
            self.logger.info(f"obs_settings loaded: {saved_settings}")
        else:
            self.obs_settings_default()
            self.logger.info(f"obs_default_settings loaded")
        if get_password(KEYRING_SERVICE_NAME, KEYRING_ROOM_INFO) is not None:
            delete_password(KEYRING_SERVICE_NAME, KEYRING_ROOM_INFO)
        self._room_info_default()
        self.logger.info(f"room_default_settings loaded")

        if self.is_new:
            self.logger.info(f"new credentials created, exiting")
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

        cookies_index = self.get_cookies_index()
        self.logger.info(f"cookies index loaded: {cookies_index}")
        if not cookies_index or (
                saved_cookies := get_password(
                    KEYRING_SERVICE_NAME,
                    cookies_index[
                        self.cookie_index])) is None:
            return
        saved_cookies = loads(saved_cookies)
        config.session.cookies.clear()
        cookiejar_from_dict(saved_cookies,
                            cookiejar=config.session.cookies)
        config.session.cookies.set("appkey", constant.APP_KEY,
                                   domain="bilibili.com", path="/")
        config.session.headers.clear()
        config.session.headers.update(constant.HEADERS_APP)
        nav_url = "https://api.bilibili.com/x/web-interface/nav"
        self.logger.info(f"nav Request")
        response = config.session.get(
            nav_url,
            params=livehime_sign({},
                                 access_key=False,
                                 build=False,
                                 version=False))
        response.encoding = "utf-8"
        self.logger.info("nav Response")
        response = response.json()
        if response["code"] != 0:
            raise CredentialExpiredError("登录凭据过期, 请重新登录")
        config.cookies_dict.clear()
        config.cookies_dict.update(saved_cookies)
        config.scan_status["scanned"] = True

    @staticmethod
    def on_finished(parent_window: "MainWindow"):
        FetchLoginWorker.post_login(parent_window)
        parent_window.load_credentials()
        panel = parent_window.panel
        panel.host_input.setText(
            config.obs_settings.get("ip_addr", "localhost"))
        panel.port_input.setText(config.obs_settings.get("port", "4455"))
        panel.pass_input.setText(config.obs_settings.get("password", ""))
        panel.obs_auto_live_checkbox.setChecked(
            config.obs_settings.get("auto_live", False))
        panel.obs_auto_connect_checkbox.setChecked(
            config.obs_settings.get("auto_connect", False))
