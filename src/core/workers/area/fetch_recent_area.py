# module import
from typing import Callable

from src.core.workers.base.BaseWorker import BaseWorker
from src.core.workers.base.Presenter import Presenter
from ... import app_state
from ...log import get_logger
from ...sign import livehime_sign


class FetchRecentAreaWorker(BaseWorker):
    def __init__(self, presenter: Presenter):
        super().__init__(name="历史分区获取", presenter=presenter)
        self.logger = get_logger(self.__class__.__name__)

    def run(self, report_progress: Callable | None, *args, **kwargs):
        session = self.require_session()
        url = "https://api.live.bilibili.com/room/v1/Area/getMyChooseArea"
        self.logger.info("getMyChooseArea Request")
        response = session.get(url, params=livehime_sign({
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
