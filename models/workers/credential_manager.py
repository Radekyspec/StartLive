from json import loads

from PySide6.QtCore import Slot
# package import
from keyring import get_password
from requests.cookies import cookiejar_from_dict

# local package import
import config
from constant import *
from exceptions import CredentialExpiredError
from .base import BaseWorker
from .fetch_login import FetchLoginWorker


class CredentialManagerWorker(BaseWorker):
    def __init__(self, parent_window: "MainWindow"):
        super().__init__(name="凭据管理")
        self.parent_window = parent_window

    @staticmethod
    def obs_default_settings():
        config.stream_settings.update({
            "ip_addr": "localhost",
            "port": "4455",
            "password": "",
            "auto_live": False,
            "auto_connect": False
        })

    @staticmethod
    def room_default_settings():
        config.room_info.update({
            "room_id": "",
            "title": "",
            "parent_area": "",
            "area": "",
        })

    @Slot()
    def run(self, /) -> None:
        try:
            if (saved_settings := get_password(KEYRING_SERVICE_NAME,
                                               KEYRING_SETTINGS)) is not None:
                config.stream_settings.update(loads(saved_settings))
            else:
                self.obs_default_settings()
            if (room_settings := get_password(KEYRING_SERVICE_NAME,
                                              KEYRING_ROOM_INFO)) is not None:
                config.room_info.update(loads(room_settings))
            else:
                self.room_default_settings()

            panel = self.parent_window.panel
            panel.host_input.setText(config.stream_settings["ip_addr"])
            panel.port_input.setText(config.stream_settings["port"])
            panel.pass_input.setText(config.stream_settings["password"])
            panel.obs_auto_live_checkbox.setChecked(
                config.stream_settings.get("auto_live", False))
            panel.obs_auto_connect_checkbox.setChecked(
                config.stream_settings.get("auto_connect", False))

            if (saved_cookies := get_password(KEYRING_SERVICE_NAME,
                                              KEYRING_COOKIES)) is not None:
                saved_cookies = loads(saved_cookies)
                cookiejar_from_dict(saved_cookies,
                                    cookiejar=config.session.cookies)
                nav_url = "https://api.bilibili.com/x/web-interface/nav"
                response = config.session.get(nav_url)
                response.encoding = "utf-8"
                response = response.json()
                if response["code"] != 0:
                    raise CredentialExpiredError("登录凭据过期, 请重新登录")
                config.cookies_dict.update(saved_cookies)
                config.scan_status["scanned"] = True
                FetchLoginWorker.post_login(self.parent_window)
        except Exception as e:
            self.exception = e
        finally:
            self.finished = True
