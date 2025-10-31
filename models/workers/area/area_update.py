# module import

# package import
from PySide6.QtCore import Slot

# local package import
import app_state
import constant
from exceptions import AreaUpdateError
from models.log import get_logger
from models.workers.base import BaseWorker, run_wrapper
from sign import livehime_sign


class AreaUpdateWorker(BaseWorker):
    def __init__(self, parent: "StreamConfigPanel", /, area: str):
        super().__init__(name="分区更新")
        self.parent = parent
        self.area = area
        self.logger = get_logger(self.__class__.__name__)

    @Slot()
    @run_wrapper
    def run(self, /) -> None:
        url = "https://api.live.bilibili.com/xlive/app-blink/v2/room/AnchorChangeRoomArea"
        area_data = {
            "area_id": app_state.area_codes[self.area],
            "build": constant.LIVEHIME_BUILD,
            "csrf_token": app_state.cookies_dict["bili_jct"],
            "csrf": app_state.cookies_dict["bili_jct"],
            "platform": "pc_link",
            "room_id": app_state.room_info["room_id"],
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
    def on_finished(self, *args, **kwargs):
        app_state.room_info[
            "parent_area"] = self.parent.parent_combo.currentText()
        app_state.room_info[
            "area"] = self.parent.child_combo.currentText()
        self._session.close()

    @Slot()
    def on_exception(self, *args, **kwargs):
        enabled = self.parent.enable_child_combo_autosave(False)
        self.parent.parent_combo.setCurrentText(
            app_state.room_info["parent_area"])
        self.parent.child_combo.setCurrentText(app_state.room_info["area"])
        self.parent.enable_child_combo_autosave(enabled)
        self.parent.modify_area_btn.setEnabled(True)
