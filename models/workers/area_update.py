# module import

# package import
from keyring import set_password
from PySide6.QtCore import Slot

# local package import
import config
import constant
from config import dumps
from constant import *
from exceptions import AreaUpdateError
from models.workers.base import BaseWorker
from models.log import get_logger
from sign import livehime_sign


class AreaUpdateWorker(BaseWorker):
    def __init__(self, parent_window: "StreamConfigPanel"):
        super().__init__(name="分区更新")
        self.parent_window = parent_window
        self.logger = get_logger(self.__class__.__name__)

    @Slot()
    def run(self, /) -> None:
        print(config.session.headers)
        url = "https://api.live.bilibili.com/xlive/app-blink/v2/room/AnchorChangeRoomArea"
        area_data = {
            "area_id": config.area_codes[
                self.parent_window.child_combo.currentText()],
            "build": constant.LIVEHIME_BUILD,
            "csrf_token": config.cookies_dict["bili_jct"],
            "csrf": config.cookies_dict["bili_jct"],
            "platform": "pc_link",
            "room_id": config.room_info["room_id"],
        }
        self.logger.info(f"AnchorChangeRoomArea Request")
        try:
            response = config.session.post(url, params=livehime_sign({}),
                                           data=area_data)
            response.encoding = "utf-8"
            self.logger.info("AnchorChangeRoomArea Response")
            # print(response.text)
            response.raise_for_status()
            response = response.json()
            self.logger.info(f"AnchorChangeRoomArea Result: {response}")
            if response["code"] != 0:
                raise AreaUpdateError(response["message"])
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
