# module import
from typing import Callable

from ..base import BaseWorker
from ... import app_state
from ...log import get_logger
from ...sign import livehime_sign


class FetchRecentAreaWorker(BaseWorker):
    def __init__(self, *args, **kwargs):
        super().__init__(name="历史分区获取", *args, **kwargs)
        self.logger = get_logger(self.__class__.__name__)

    def run(self, report_progress: Callable | None, *args, **kwargs):
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
        self._session.close()
