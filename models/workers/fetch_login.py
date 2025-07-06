# module import
from json import dumps
from time import sleep

from PySide6.QtCore import Slot
# package import
from keyring import set_password

# local package import
import config
from constant import *
from exceptions import LoginError
from models.log import get_logger
from models.workers.base import LongLiveWorker
from .fetch_pre_live import FetchPreLiveWorker


class FetchLoginWorker(LongLiveWorker):
    def __init__(self, parent_window: "MainWindow"):
        super().__init__(name="登录")
        self.parent_window = parent_window
        self.logger = get_logger(self.__class__.__name__)

    @classmethod
    def _fetch_area_id(cls):
        logger = get_logger(cls.__name__)
        url = "https://api.live.bilibili.com/room/v1/Area/getList"
        logger.info(f"Area/getList Request")
        response = config.session.get(url)
        response.encoding = "utf-8"
        logger.info("Area/getList Response")
        response = response.json()
        for area_info in response["data"]:
            config.parent_area.append(area_info["name"])
            config.area_options[area_info["name"]] = []
            for sub_area in area_info["list"]:
                config.area_codes[sub_area["name"]] = sub_area["id"]
                config.area_options[area_info["name"]].append(sub_area["name"])
        config.scan_status["area_updated"] = True

    @staticmethod
    def post_login(parent: "MainWindow"):
        parent.add_thread(FetchPreLiveWorker(parent.panel))
        FetchLoginWorker._fetch_area_id()
        set_password(KEYRING_SERVICE_NAME, KEYRING_COOKIES,
                     dumps(config.cookies_dict))

    @Slot()
    def run(self, /) -> None:
        check_url = "https://passport.bilibili.com/x/passport-login/web/qrcode/poll"
        while config.scan_status["qr_key"] is None and self.is_running:
            sleep(0.1)
        params = {
            "qrcode_key": config.scan_status["qr_key"],
            "source": "live_pc",
            "web_location": "0.0"
        }
        try:
            while not config.scan_status["scanned"] and self.is_running:
                self.logger.info("QR poll Request")
                response = config.session.get(check_url, params=params)
                response.encoding = "utf-8"
                self.logger.info("QR poll Response")
                result = response.json()
                match result["data"]["code"]:
                    case 86101:  # Not scanned yet
                        self.logger.info(f"QR poll Result: {result}")
                        sleep(1)
                        continue
                    case 86038:  # QR expired
                        self.logger.info(f"QR poll Result: {result}")
                        config.scan_status["timeout"] = True
                        break
                    case 86090:  # Scanned but not confirmed
                        self.logger.info(f"QR poll Result: {result}")
                        config.scan_status["wait_for_confirm"] = True
                        sleep(1)
                    case 0:  # Login successful
                        config.cookies_dict = response.cookies.get_dict()
                        # config.cookies_dict["refresh_token"] = result["data"][
                        #     "refresh_token"]
                        config.scan_status["scanned"] = True
                        self.post_login(self.parent_window)
                        break
                    case _:
                        raise LoginError(result["message"])
        except Exception as e:
            self.exception = e
        finally:
            self.finished = True
