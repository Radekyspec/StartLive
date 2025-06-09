# module import

# package import
from PySide6.QtCore import Slot

# local package import
import config
from constant import *
from sign import livehime_sign
from .base import BaseWorker


class AreaUpdateWorker(BaseWorker):
    def __init__(self, parent_window: "StreamConfigPanel"):
        super().__init__(name="标题更新")
        self.parent_window = parent_window

    @Slot()
    def run(self, /) -> None:
        url = "https://api.live.bilibili.com/xlive/app-blink/v2/room/AnchorChangeRoomArea"
        area_data = {
            "area_id": config.area_codes[
                self.parent_window.child_combo.currentText()],
            "build": LIVEHIME_BUILD,
            "csrf_token": config.cookies_dict["bili_jct"],
            "csrf": config.cookies_dict["bili_jct"],
            "platform": "pc_link",
            "room_id": config.room_info["room_id"],
        }
        try:
            response = config.session.post(url, params=livehime_sign({}),
                                           data=area_data)
            response.encoding = "utf-8"
            # print(response.text)
            response.raise_for_status()
            if (response := response.json())["code"] != 0:
                raise ValueError(response["message"])
        except Exception as e:
            self.exception = e
            self.parent_window.save_area_btn.setEnabled(True)
        finally:
            self.finished = True
