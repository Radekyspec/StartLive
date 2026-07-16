# module import
from time import sleep
from typing import Callable

# local package import
from src.core import app_state
from src.core.constant import FaceAuthType
# package import
from src.core.log import get_logger
from src.core.sign import gen_dm_track
from src.core.workers.base import LongLiveWorker, Presenter


class FaceAuthWorker(LongLiveWorker):
    def __init__(self, presenter: Presenter, /, auth_type: FaceAuthType):
        super().__init__(name="人脸认证", presenter=presenter)
        self._auth_type = auth_type
        self.logger = get_logger(self.__class__.__name__)

    def run(self, report_progress: Callable | None, *args, **kwargs):
        if self._auth_type == FaceAuthType.V2:
            return self._face_auth_v2_precheck()

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
        return None

    def _face_auth_v2_precheck(self):
        url = "https://api.bilibili.com/x/gaia-vgate/v2/validatePreCheck"
        verify_params = {
            "token": app_state.stream_status.face_voucher,
            "dm_track": gen_dm_track(),
            "csrf": app_state.cookies_dict["bili_jct"]
        }
        verified = False
        while self.is_running and not verified:
            self.logger.info("validatePreCheck Request")
            response = self._session.post(url, data=verify_params)
            self.logger.info("validatePreCheck Response")
            response.encoding = "utf-8"
            response = response.json()
            self.logger.info(f"validatePreCheck Result: {response}")
            if response["data"] and response["data"]["status"] == 1:
                verified = True
            sleep(1)
