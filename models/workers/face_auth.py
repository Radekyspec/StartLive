# module import
from contextlib import suppress
from time import sleep

# package import
from PySide6.QtCore import Slot

# local package import
import config
from models.log import get_logger
from models.workers.base import LongLiveWorker, run_wrapper


class FaceAuthWorker(LongLiveWorker):
    def __init__(self, qr_window: "FaceQRWidget"):
        super().__init__(name="人脸认证")
        self.qr_window = qr_window
        self.logger = get_logger(self.__class__.__name__)

    @Slot()
    @run_wrapper
    def run(self, /) -> None:
        url = "https://api.live.bilibili.com/xlive/app-blink/v1/preLive/IsUserIdentifiedByFaceAuth"
        verify_data = {
            "room_id": config.room_info["room_id"],
            "face_auth_code": "60024",
            "csrf_token": config.cookies_dict["bili_jct"],
            "csrf": config.cookies_dict["bili_jct"],
            "visit_id": "",
        }
        verified = False
        while self.is_running and not verified and self.qr_window:
            self.logger.info("IsUserIdentifiedByFaceAuth Request")
            response = config.session.post(url, data=verify_data)
            response.encoding = "utf-8"
            self.logger.info("IsUserIdentifiedByFaceAuth Response")
            response = response.json()
            self.logger.info(f"IsUserIdentifiedByFaceAuth Result: {response}")
            if response["data"] and response["data"]["is_identified"]:
                verified = True
            sleep(1)

    @staticmethod
    def on_finished(qr_window: "FaceQRWidget"):
        with suppress(RuntimeError):
            qr_window.deleteLater()
