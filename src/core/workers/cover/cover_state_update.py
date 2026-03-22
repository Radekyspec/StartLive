# module import
from time import sleep
from typing import Callable

# local package import
from src.core import app_state
# package import
from src.core.log import get_logger
from src.core.sign import livehime_sign
from src.core.workers.base import LongLiveWorker


class CoverStateUpdateWorker(LongLiveWorker):
    def __init__(self, *args, **kwargs):
        super().__init__(name="封面审核更新", *args, **kwargs)
        self.logger = get_logger(self.__class__.__name__)

    def run(self, report_progress: Callable | None, *args, **kwargs):
        while self.is_running and app_state.room_info["cover_status"] == 0:
            url = "https://api.live.bilibili.com/xlive/app-blink/v1/preLive/PreLive"
            params = livehime_sign({
                "area": "true",
                "cover": "true",
                "coverVertical": "true",
                "liveDirectionType": 0,
                "mobi_app": "pc_link",
                "schedule": "true",
                "title": "true",
            })
            self.logger.info("PreLive Request")
            response = self._session.get(url, params=params)
            response.encoding = "utf-8"
            self.logger.info("PreLive Response")
            response = response.json()
            self.logger.info(f"PreLive Result: {response}")
            app_state.room_info.update({
                "cover_audit_reason": response["data"]["cover"]["auditReason"],
                "cover_url": response["data"]["cover"]["url"],
                "cover_status": response["data"]["cover"]["auditStatus"],
                "title": response["data"]["title"],
            })
            sleep(3)
        self._session.close()
