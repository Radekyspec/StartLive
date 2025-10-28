# module import
from PySide6.QtCore import Slot
from PySide6.QtGui import QIntValidator
from PySide6.QtWidgets import QLineEdit

# local package import
import app_state
from models.log import get_logger
from models.workers.base import BaseWorker, run_wrapper
from sign import livehime_sign


class FetchStreamTimeShiftWorker(BaseWorker):
    def __init__(self):
        super().__init__(name="推流延迟获取")
        self.logger = get_logger(self.__class__.__name__)
        self._min_time_shift = 10
        self._max_time_shift = 300
        self._time_shift = 0

    @Slot()
    @run_wrapper
    def run(self, /) -> None:
        url = "https://api.live.bilibili.com/xlive/app-blink/v1/upStreamConfig/GetAnchorSelfStreamTimeShift"
        self.logger.info(f"AnchorSelfStreamTimeShift Request")
        response = self._session.get(url, params=livehime_sign({
            "csrf": app_state.cookies_dict["bili_jct"],
            "csrf_token": app_state.cookies_dict["bili_jct"],
            "room_id": app_state.room_info["room_id"],
        }))
        response.encoding = "utf-8"
        self.logger.info("AnchorSelfStreamTimeShift Response")
        response = response.json()
        if response["code"] != 0:
            raise ValueError(response["message"])
        self._time_shift = response["data"]["time_shift"]
        self._min_time_shift = response["data"]["min_time_shift"]
        self._max_time_shift = response["data"]["max_time_shift"]

    @Slot()
    def on_finished(self, delay_edit: QLineEdit, /, *args, **kwargs):
        delay_edit.setValidator(
            QIntValidator(self._min_time_shift, self._max_time_shift,
                          delay_edit))
        delay_edit.setText(str(self._time_shift))
        self._session.close()
