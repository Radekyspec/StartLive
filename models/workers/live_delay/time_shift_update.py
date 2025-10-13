# module import
from PySide6.QtCore import Slot
from PySide6.QtWidgets import QPushButton

# local package import
import config
from models.log import get_logger
from models.workers.base import BaseWorker, run_wrapper
from sign import livehime_sign


class StreamTimeShiftUpdateWorker(BaseWorker):
    def __init__(self, delay: str):
        super().__init__(name="推流延迟更新")
        self.logger = get_logger(self.__class__.__name__)
        self._delay = delay

    @Slot()
    @run_wrapper
    def run(self, /) -> None:
        url = "https://api.live.bilibili.com/xlive/app-blink/v1/upStreamConfig/SetAnchorSelfStreamTimeShift"
        self.logger.info(f"SetAnchorSelfStreamTimeShift Request")
        response = self._session.post(url, data=livehime_sign({
            "csrf": config.cookies_dict["bili_jct"],
            "csrf_token": config.cookies_dict["bili_jct"],
            "room_id": config.room_info["room_id"],
            "time_shift": self._delay,
        }))
        response.encoding = "utf-8"
        self.logger.info("SetAnchorSelfStreamTimeShift Response")
        response = response.json()
        if response["code"] != 0:
            raise ValueError(response["message"])

    @Slot()
    def on_finished(self):
        self._session.close()

    @Slot()
    def on_exception(self, save_btn: QPushButton, /, *args, **kwargs):
        save_btn.setEnabled(True)
