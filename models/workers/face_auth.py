# module import
from contextlib import suppress
from time import sleep

# package import
from PySide6.QtCore import Slot

# local package import
import config
from .base import LongLiveWorker


class FaceAuthWorker(LongLiveWorker):
    def __init__(self, qr_window: "FaceQRWidget"):
        super().__init__(name="人脸认证")
        self.qr_window = qr_window

    @Slot()
    def run(self, /) -> None:
        try:
            url = "https://api.live.bilibili.com/xlive/app-blink/v1/preLive/IsUserIdentifiedByFaceAuth"
            verify_data = {
                "room_id": config.room_info["room_id"],
                "face_auth_code": "60024",
                "csrf_token": config.cookies_dict["bili_jct"],
                "csrf": config.cookies_dict["bili_jct"],
                "visit_id": "",
            }
            verified = False
            while self._is_running and not verified and self.qr_window:
                response = config.session.post(url, data=verify_data)
                response.encoding = "utf-8"
                response = response.json()
                for key in response["data"]:
                    if response["data"][key]:
                        verified = True
                sleep(1)
        except Exception as e:
            self.exception = e
        finally:
            with suppress(RuntimeError):
                self.qr_window.deleteLater()
            self.finished = True
