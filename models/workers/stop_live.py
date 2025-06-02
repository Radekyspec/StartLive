# module import

# package import
from PySide6.QtCore import Slot

# local package import
import config
from .base import BaseWorker
from sign import livehime_sign, order_payload


class StopLiveWorker(BaseWorker):
    def __init__(self, parent_window: "StreamConfigPanel"):
        super().__init__(name="停播任务")
        self.parent_window = parent_window

    @Slot()
    def run(self, /) -> None:
        url = "https://api.live.bilibili.com/room/v1/Room/stopLive"
        stop_data = livehime_sign({
            "room_id": config.room_info["room_id"],
        })
        stop_data.update({
            "csrf_token": config.cookies_dict["bili_jct"],
            "csrf": config.cookies_dict["bili_jct"]
        })
        stop_data = order_payload(stop_data)
        try:
            response = config.session.post(url, data=stop_data)
            response.encoding = "utf-8"
            response = response.json()
            if response["code"] != 0:
                raise ValueError(response["message"])
        except Exception as e:
            self.parent_window.start_btn.setEnabled(False)
            self.parent_window.stop_btn.setEnabled(True)
            # self.parent_window.parent_combo.setEnabled(False)
            # self.parent_window.child_combo.setEnabled(False)
            self.parent_window.save_area_btn.setEnabled(True)
            self.exception = e
        finally:
            self.finished = True
