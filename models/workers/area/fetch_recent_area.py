# module import
from PySide6.QtCore import Slot

# local package import
import app_state
from models.log import get_logger
from models.workers.base import BaseWorker, run_wrapper
from sign import livehime_sign


class FetchRecentAreaWorker(BaseWorker):
    def __init__(self):
        super().__init__(name="历史分区获取")
        self.logger = get_logger(self.__class__.__name__)

    @Slot()
    @run_wrapper
    def run(self, /) -> None:
        url = "https://api.live.bilibili.com/room/v1/Area/getMyChooseArea"
        self.logger.info("getMyChooseArea Request")
        response = self._session.get(url, params=livehime_sign({
            "roomid": app_state.room_info["room_id"],
        }))
        self.logger.info("getMyChooseArea Response")
        response = response.json()
        if response["code"] != 0:
            raise ValueError(response["message"])
        app_state.room_info["recent_areas"].clear()
        for area_data in response["data"]:
            app_state.room_info["recent_areas"].append(
                (area_data["parent_name"], area_data["name"]))

    @Slot()
    def on_finished(self, dlg: "AreaPickerPanel", /, *args, **kwargs):
        dlg.historyUpdated.emit(app_state.room_info["recent_areas"])
        self._session.close()
