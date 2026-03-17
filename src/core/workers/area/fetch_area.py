# module import
from PySide6.QtCore import Slot
from src.models.log import get_logger
from src.models.states import LoginState
from src.sign import livehime_sign

# local package import
from src import app_state
from src.core.workers.base import BaseWorker, run_wrapper


class FetchAreaWorker(BaseWorker):
    def __init__(self, state: LoginState):
        super().__init__(name="分区获取")
        self.state = state
        self.logger = get_logger(self.__class__.__name__)

    @Slot()
    @run_wrapper
    def run(self, /) -> None:
        url = "https://api.live.bilibili.com/xlive/app-blink/v1/preLive/GetAreaListForLive"
        self.logger.info(f"Area/getList Request")
        response = self._session.get(url, params=livehime_sign({}))
        response.encoding = "utf-8"
        self.logger.info("Area/getList Response")
        response = response.json()
        for area_info in response["data"]["area_v1_info"]:
            parent = area_info["name"]
            app_state.parent_area.append(parent)
            app_state.area_options[parent] = []
            for sub_area in area_info["list"]:
                app_state.area_codes[sub_area["name"]] = sub_area["id"]
                app_state.area_options[area_info["name"]].append(
                    sub_area["name"])
                app_state.area_reverse[sub_area["name"]] = parent
        app_state.scan_status["area_updated"] = True

    @Slot()
    def on_finished(self):
        self.state.areaUpdated.emit()
        self._session.close()
