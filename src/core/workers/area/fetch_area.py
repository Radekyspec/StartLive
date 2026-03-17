# module import
from typing import Callable

# local package import
from ... import app_state
from ...log import get_logger
from ...sign import livehime_sign
from ...workers.base import BaseWorker


class FetchAreaWorker(BaseWorker):
    def __init__(self, *args, **kwargs):
        super().__init__(name="分区获取", *args, **kwargs)
        self.logger = get_logger(self.__class__.__name__)

    def run(self, report_progress: Callable | None, *args, **kwargs):
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
        self._session.close()
