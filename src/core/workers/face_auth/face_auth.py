# module import
from time import sleep
from typing import Callable

# local package import
from src.core import app_state
# package import
from src.core.log import get_logger
from src.core.workers.base import LongLiveWorker


class FaceAuthWorker(LongLiveWorker):
    def __init__(self, ):
        super().__init__(name="人脸认证")
        self.logger = get_logger(self.__class__.__name__)

    def run(self, report_progress: Callable | None, *args, **kwargs) -> None:
        url = "https://api.live.bilibili.com/xlive/app-blink/v1/preLive/IsUserIdentifiedByFaceAuth"
        verify_data = {
            "room_id": app_state.room_info["room_id"],
            "face_auth_code": "60024",
            "csrf_token": app_state.cookies_dict["bili_jct"],
            "csrf": app_state.cookies_dict["bili_jct"],
            "visit_id": "",
        }
        verified = False
        while self.is_running and not verified:
            self.logger.info("IsUserIdentifiedByFaceAuth Request")
            response = self._session.post(url, data=verify_data)
            response.encoding = "utf-8"
            self.logger.info("IsUserIdentifiedByFaceAuth Response")
            response = response.json()
            self.logger.info(f"IsUserIdentifiedByFaceAuth Result: {response}")
            if response["data"] and response["data"]["is_identified"]:
                verified = True
            sleep(1)
        self._session.close()
