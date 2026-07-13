# module import
from typing import Callable

# local package import
from src.core import app_state
from src.core.log import get_logger
from src.core.sign import livehime_sign
from src.core.workers.base import BaseWorker, Presenter


class FetchStreamTimeShiftWorker(BaseWorker):
    def __init__(self, presenter: Presenter):
        super().__init__(name="推流延迟获取", presenter=presenter)
        self.logger = get_logger(self.__class__.__name__)

    def run(self, report_progress: Callable | None, *args, **kwargs):
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
        return response["data"]["time_shift"], response["data"][
            "min_time_shift"], response["data"]["max_time_shift"]
