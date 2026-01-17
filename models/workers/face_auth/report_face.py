from PySide6.QtCore import Slot

# local package import
import app_state
from models.log import get_logger
from models.workers.base import BaseWorker, run_wrapper
from sign import livehime_sign, order_payload


class ReportFaceRecognitionWorker(BaseWorker):
    def __init__(self, area: int, message: str):
        super().__init__(name="人脸报告")
        self.area = area
        self.message = message
        self.logger = get_logger(self.__class__.__name__)

    @Slot()
    @run_wrapper
    def run(self, /) -> None:
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

    @Slot()
    def on_finished(self):
        self._session.close()
