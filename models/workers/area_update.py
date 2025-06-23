# module import

# package import
from keyring import set_password
from PySide6.QtCore import Slot

# local package import
import config
from constant import *
from models.classes import dumps
from sign import livehime_sign
from .base import BaseWorker


class AreaUpdateWorker(BaseWorker):
    def __init__(self, parent_window: "StreamConfigPanel"):
        super().__init__(name="分区更新")
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
            config.room_info[
                "parent_area"] = self.parent_window.parent_combo.currentText()
            config.room_info[
                "area"] = self.parent_window.child_combo.currentText()
            set_password(KEYRING_SERVICE_NAME, KEYRING_ROOM_INFO,
                         dumps(config.room_info.internal))
        except Exception as e:
            self.exception = e
            self.parent_window.save_area_btn.setEnabled(True)
        finally:
            self.finished = True
