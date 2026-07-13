# package import
from typing import Callable

# local package import
from src.core import app_state, constant
from src.core.exceptions import StopLiveError
from src.core.log import get_logger
from src.core.sign import livehime_sign, order_payload
from src.core.workers.base import BaseWorker, Presenter


class StopLiveWorker(BaseWorker):
    def __init__(self, presenter: Presenter):
        super().__init__(name="停播任务", presenter=presenter)
        self.logger = get_logger(self.__class__.__name__)

    def run(self, report_progress: Callable | None, *args, **kwargs):

        url = "https://api.live.bilibili.com/room/v1/Room/stopLive"
        # [0.3.5]: Watch here because in livehime ver 9240
        # startLive needs csrf to sign but stopLive not
        if constant.STOP_LIVE_AUTH_CSRF:
            self.logger.info("stopLive sign with csrf")
            stop_data = livehime_sign({
                "csrf_token": app_state.cookies_dict["bili_jct"],
                "csrf": app_state.cookies_dict["bili_jct"],
                "room_id": app_state.room_info["room_id"],
            })
        else:
            self.logger.info("stopLive sign without csrf")
            stop_data = livehime_sign({
                "room_id": app_state.room_info["room_id"],
            })

            stop_data.update({
                "csrf_token": app_state.cookies_dict["bili_jct"],
                "csrf": app_state.cookies_dict["bili_jct"]
            })
            stop_data = order_payload(stop_data)
        self.logger.info(f"stopLive Request")
        response = self._session.post(url, data=stop_data)
        response.encoding = "utf-8"
        self.logger.info("stopLive Response")
        response = response.json()
        self.logger.info(f"stopLive Result: {response}")
        if response["code"] != 0:
            raise StopLiveError(response["message"])
