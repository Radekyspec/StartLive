# module import
from typing import Callable

from ..base import BaseWorker
from ... import app_state
from ...log import get_logger
from ...sign import livehime_sign


class FetchAnnounceWorker(BaseWorker):
    def __init__(self, *args, **kwargs):
        super().__init__(name="主播公告获取", *args, **kwargs)
        self.logger = get_logger(self.__class__.__name__)

    def run(self, report_progress: Callable | None, *args, **kwargs):
        url = "https://api.live.bilibili.com/xlive/app-blink/v1/room/AnnounceInfo"
        self.logger.info(f"Announcement info Request")
        params = livehime_sign({})
        response = self._session.get(url, params=params)
        response.encoding = "utf-8"
        self.logger.info("Announcement info Response")
        response = response.json()
        self.logger.info(f"Announcement info Result: {response}")
        content: dict = response["data"]["announces"]
        app_state.room_info["announcement"] = content.get("1", {}).get(
            "content", ""
        )
        app_state.scan_status["announce_updated"] = True
        self._session.close()
