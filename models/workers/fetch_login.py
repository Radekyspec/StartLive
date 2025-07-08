# module import
from functools import partial
from time import sleep

# package import
from PySide6.QtCore import Slot

# local package import
import config
from exceptions import LoginError
from models.log import get_logger
from models.workers.base import LongLiveWorker, run_wrapper
from .fetch_area import FetchAreaWorker
from .fetch_pre_live import FetchPreLiveWorker


class FetchLoginWorker(LongLiveWorker):
    def __init__(self):
        super().__init__(name="登录")
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
        if config.scan_status["scanned"]:
            parent.add_thread(
                FetchPreLiveWorker(),
                on_finished=partial(FetchPreLiveWorker.on_finished,
                                    parent.panel)
            )
            parent.add_thread(FetchAreaWorker())

    @Slot()
    @run_wrapper
    def run(self, /) -> None:
        check_url = "https://passport.bilibili.com/x/passport-login/web/qrcode/poll"
        while config.scan_status["qr_key"] is None and self.is_running:
            sleep(0.1)
        params = {
            "qrcode_key": config.scan_status["qr_key"],
            "source": "live_pc",
            "web_location": "0.0"
        }
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
                    continue
                case 0:  # Login successful
                    config.cookies_dict = response.cookies.get_dict()
                    # config.cookies_dict["refresh_token"] = result["data"][
                    #     "refresh_token"]
                    config.scan_status["scanned"] = True
                    from .credential_manager import CredentialManagerWorker
                    CredentialManagerWorker.add_cookie()
                    break
                case _:
                    raise LoginError(result["message"])

    @staticmethod
    def on_finished(parent_window: "MainWindow"):
        FetchLoginWorker.post_login(parent_window)
