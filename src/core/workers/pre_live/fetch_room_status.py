from PySide6.QtCore import Slot
from models.log import get_logger
# local package import
from src.exceptions import RoomStatusError
from src.sign import livehime_sign

from src.core.workers.base import BaseWorker, run_wrapper


class FetchRoomStatusWorker(BaseWorker):
    def __init__(self):
        super().__init__(name="房间信息检查")
        self.logger = get_logger(self.__class__.__name__)

    @Slot()
    @run_wrapper
    def run(self, /) -> None:
        url = "https://api.live.bilibili.com/xlive/app-blink/v1/index/GetRoomPreLiveStatus"
        self.logger.info(f"GetRoomPreLiveStatus Request")
        response = self._session.get(url, params=livehime_sign({},
                                                               access_key=False))
        response.encoding = "utf-8"
        self.logger.info("GetRoomPreLiveStatus Response")
        response = response.json()
        self.logger.info(f"GetRoomPreLiveStatus Result: {response}")
        if response["code"] != 0:
            raise RoomStatusError(response["message"])

    @Slot()
    def on_finished(self):
        self._session.close()
