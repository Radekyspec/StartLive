from json import loads

from PySide6.QtCore import Slot
# package import
from keyring import get_password, set_password, delete_password
from requests.cookies import cookiejar_from_dict

# local package import
import config
from config import dumps
from constant import *
from exceptions import CredentialExpiredError
from models.log import get_logger
from models.workers.base import BaseWorker, run_wrapper
from .fetch_login import FetchLoginWorker


class CredentialManagerWorker(BaseWorker):
    def __init__(self, cookie_index: int | None = None, is_new: bool = False):
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
    def room_info_default():
        config.room_info.update({
            "room_id": "",
            "title": "",
            "parent_area": "",
            "area": "",
        })

    @staticmethod
    def scan_settings_default():
        config.scan_status.update({
            "scanned": False, "qr_key": None, "qr_url": None,
            "timeout": False, "wait_for_confirm": False,
            "area_updated": False, "room_updated": False,
            "const_updated": True
        })

    @staticmethod
    def stream_status_default():
        config.stream_status.update({
            "live_status": False,
            "required_face": False,
            "identified_face": False,
            "face_url": None,
            "stream_addr": None,
            "stream_key": None
        })

    @staticmethod
    def add_cookie():
        """
        Adding cookie from config.cookies_dict to keyring
        :return:
        """
        uid = config.cookies_dict["DedeUserID"]
        set_password(KEYRING_SERVICE_NAME, f"cookies|{uid}",
                     dumps(config.cookies_dict))
        cookies_index = CredentialManagerWorker.get_cookies_index()
        cookies_index.append(f"cookies|{uid}")
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
        self.room_info_default()
        self.logger.info(f"room_default_settings loaded")
        if self.is_new:
            self.logger.info(f"new credentials created, exiting")
            return
        if (saved_cookies := get_password(KEYRING_SERVICE_NAME,
                                          KEYRING_COOKIES)) is not None and \
                get_password(KEYRING_SERVICE_NAME,
                             KEYRING_COOKIES_INDEX) is None:
            # Old version cookie storage, change to index
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
        if cookies_index:
            if self.cookie_index is None:
                cookie_index = cookies_index[0]
            else:
                cookie_index = cookies_index[self.cookie_index]
            if (saved_cookies := get_password(KEYRING_SERVICE_NAME,
                                              cookie_index)) is None:
                return
            saved_cookies = loads(saved_cookies)
            config.session.cookies.clear()
            cookiejar_from_dict(saved_cookies,
                                cookiejar=config.session.cookies)
            nav_url = "https://api.bilibili.com/x/web-interface/nav"
            self.logger.info(f"nav Request")
            response = config.session.get(nav_url)
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
        panel.host_input.setText(config.obs_settings["ip_addr"])
        panel.port_input.setText(config.obs_settings["port"])
        panel.pass_input.setText(config.obs_settings["password"])
        panel.obs_auto_live_checkbox.setChecked(
            config.obs_settings.get("auto_live", False))
        panel.obs_auto_connect_checkbox.setChecked(
            config.obs_settings.get("auto_connect", False))
