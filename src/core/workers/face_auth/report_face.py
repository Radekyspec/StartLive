from typing import Callable

# local package import
from src.core import app_state
from src.core.log import get_logger
from src.core.sign import livehime_sign, order_payload
from src.core.workers.base import BaseWorker


class ReportFaceRecognitionWorker(BaseWorker):
    def __init__(self, area: int, message: str):
        super().__init__(name="人脸报告")
        self.area = area
        self.message = message
        self.logger = get_logger(self.__class__.__name__)

    def run(self, report_progress: Callable | None, *args, **kwargs) -> None:
        url = "https://api.live.bilibili.com/xlive/app-blink/v1/preLive/ReportFaceRecognition"
        self.logger.info("ReportFaceRecognition Request")
        report_data = livehime_sign({})
        report_data.update({
            "area_v2_id": self.area,
            "csrf": app_state.cookies_dict["bili_jct"],
            "csrf_token": app_state.cookies_dict["bili_jct"],
            "face_auth_code": 60024,
            "face_auth_message": self.message,
            "room_id": app_state.room_info.room_id,
            "scene": "startLive"
        })
        response = self._session.post(url, data=order_payload(report_data))
        self.logger.info("ReportFaceRecognition Response")
        self.logger.info(response.text)
        if (response := response.json())["code"] != 0:
            raise ValueError(response["message"])
        self._session.close()
