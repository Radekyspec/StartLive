from typing import Callable

# local package import
from startlive.core.exceptions import RoomStatusError
from startlive.core.log import get_logger
from startlive.core.sign import livehime_sign
from startlive.core.workers.base import BaseWorker


class FetchRoomStatusWorker(BaseWorker):
    def __init__(self):
        super().__init__(name="房间信息检查")
        self.logger = get_logger(self.__class__.__name__)

    def run(self, report_progress: Callable | None, *args, **kwargs):
        url = "https://api.live.bilibili.com/xlive/app-blink/v1/index/GetRoomPreLiveStatus"
        self.logger.info(f"GetRoomPreLiveStatus Request")
        response = self._session.get(url,
                                     params=livehime_sign({}, access_key=False))
        response.encoding = "utf-8"
        self.logger.info("GetRoomPreLiveStatus Response")
        response = response.json()
        self.logger.info(f"GetRoomPreLiveStatus Result: {response}")
        if response["code"] != 0:
            raise RoomStatusError(response["message"])
