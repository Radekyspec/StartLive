# module import
from typing import Callable

from src.core.workers.base.BaseWorker import BaseWorker
from src.core.workers.base.Presenter import Presenter
from ... import app_state
from ...log import get_logger
from ...sign import livehime_sign


class FetchAnnounceWorker(BaseWorker):
    def __init__(self, presenter: Presenter):
        super().__init__(name="主播公告获取", presenter=presenter)
        self.logger = get_logger(self.__class__.__name__)

    def run(self, report_progress: Callable | None, *args, **kwargs):
        session = self.require_session()
        url = "https://api.live.bilibili.com/xlive/app-blink/v1/room/AnnounceInfo"
        self.logger.info("Announcement info Request")
        params = livehime_sign({})
        response = session.get(url, params=params)
        response.encoding = "utf-8"
        self.logger.info("Announcement info Response")
        response = response.json()
        self.logger.info(f"Announcement info Result: {response}")
        content: dict = response["data"]["announces"]
        app_state.room_info["announcement"] = content.get("1", {}).get(
            "content", ""
        )
        app_state.scan_status["announce_updated"] = True
