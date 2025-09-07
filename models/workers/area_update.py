# module import

# package import
from PySide6.QtCore import Slot

# local package import
import config
import constant
from exceptions import AreaUpdateError
from models.log import get_logger
from models.workers.base import BaseWorker, run_wrapper
from sign import livehime_sign


class AreaUpdateWorker(BaseWorker):
    def __init__(self, area: str):
        super().__init__(name="分区更新")
        self.area = area
        self.logger = get_logger(self.__class__.__name__)

    @Slot()
    @run_wrapper
    def run(self, /) -> None:
        url = "https://api.live.bilibili.com/xlive/app-blink/v2/room/AnchorChangeRoomArea"
        area_data = {
            "area_id": config.area_codes[self.area],
            "build": constant.LIVEHIME_BUILD,
            "csrf_token": config.cookies_dict["bili_jct"],
            "csrf": config.cookies_dict["bili_jct"],
            "platform": "pc_link",
            "room_id": config.room_info["room_id"],
        }
        self.logger.info(f"AnchorChangeRoomArea Request")
        response = self._session.post(url, params=livehime_sign({}),
                                      data=area_data)
        response.encoding = "utf-8"
        self.logger.info("AnchorChangeRoomArea Response")
        # print(response.text)
        response.raise_for_status()
        response = response.json()
        self.logger.info(f"AnchorChangeRoomArea Result: {response}")
        if response["code"] != 0:
            raise AreaUpdateError(response["message"])

    @Slot()
    def on_finished(self, parent_window: "StreamConfigPanel"):
        config.room_info[
            "parent_area"] = parent_window.parent_combo.currentText()
        config.room_info[
            "area"] = parent_window.child_combo.currentText()
        self._session.close()

    @staticmethod
    @Slot()
    def on_exception(parent_window: "StreamConfigPanel", *args, **kwargs):
        parent_window.save_area_btn.setEnabled(True)
