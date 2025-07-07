# module import

# package import
from PySide6.QtCore import Slot

# local package import
import config
import constant
from exceptions import StopLiveError
from sign import livehime_sign, order_payload
from models.log import get_logger
from models.workers.base import BaseWorker, run_wrapper


class StopLiveWorker(BaseWorker):
    def __init__(self):
        super().__init__(name="停播任务")
        self.logger = get_logger(self.__class__.__name__)

    @Slot()
    @run_wrapper
    def run(self, /) -> None:
        url = "https://api.live.bilibili.com/room/v1/Room/stopLive"
        # [0.3.5]: Watch here because in livehime ver 9240
        # startLive needs csrf to sign but stopLive not
        if constant.STOP_LIVE_AUTH_CSRF:
            self.logger.info("stopLive sign with csrf")
            stop_data = livehime_sign({
                "csrf_token": config.cookies_dict["bili_jct"],
                "csrf": config.cookies_dict["bili_jct"],
                "room_id": config.room_info["room_id"],
            })
        else:
            self.logger.info("stopLive sign without csrf")
            stop_data = livehime_sign({
                "room_id": config.room_info["room_id"],
            })

            stop_data.update({
                "csrf_token": config.cookies_dict["bili_jct"],
                "csrf": config.cookies_dict["bili_jct"]
            })
            stop_data = order_payload(stop_data)
        self.logger.info(f"stopLive Request")
        response = config.session.post(url, data=stop_data)
        response.encoding = "utf-8"
        self.logger.info("stopLive Response")
        response = response.json()
        self.logger.info(f"stopLive Result: {response}")
        if response["code"] != 0:
            raise StopLiveError(response["message"])

    @staticmethod
    def on_exception(parent_window: "StreamConfigPanel", *args, **kwargs):
        parent_window.start_btn.setEnabled(False)
        parent_window.stop_btn.setEnabled(True)
        # parent_window.parent_combo.setEnabled(False)
        # parent_window.child_combo.setEnabled(False)
        parent_window.save_area_btn.setEnabled(True)