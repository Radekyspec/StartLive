# module import
from typing import Callable

# local package import
from src.core import app_state
from src.core.log import get_logger
from src.core.sign import livehime_sign
from src.core.workers.base import BaseWorker, Presenter


class StreamTimeShiftUpdateWorker(BaseWorker):
    def __init__(self, presenter: Presenter, /, delay: str):
        super().__init__(name="推流延迟更新", presenter=presenter)
        self.logger = get_logger(self.__class__.__name__)
        self._delay = delay

    def run(self, report_progress: Callable | None, *args, **kwargs):
        if app_state.cookies_dict.get("bili_jct", None) is None:
            return
        url = "https://api.live.bilibili.com/xlive/app-blink/v1/upStreamConfig/SetAnchorSelfStreamTimeShift"
        self.logger.info(f"SetAnchorSelfStreamTimeShift Request")
        response = self._session.post(url, data=livehime_sign({
            "csrf": app_state.cookies_dict["bili_jct"],
            "csrf_token": app_state.cookies_dict["bili_jct"],
            "room_id": app_state.room_info["room_id"],
            "time_shift": self._delay,
        }))
        response.encoding = "utf-8"
        self.logger.info("SetAnchorSelfStreamTimeShift Response")
        response = response.json()
        if response["code"] != 0:
            raise ValueError(response["message"])
