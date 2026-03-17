# module import
from typing import Callable

from ... import app_state, constant
from ...exceptions import AreaUpdateError
from ...log import get_logger
from ...sign import livehime_sign
from ...workers.base import BaseWorker


class AreaUpdateWorker(BaseWorker):
    def __init__(self, area: str, *args, **kwargs):
        super().__init__(name="分区更新", *args, **kwargs)
        self.area = area
        self.logger = get_logger(self.__class__.__name__)

    def run(self, report_progress: Callable | None, *args, **kwargs):
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
        self._session.close()
        return self.area
