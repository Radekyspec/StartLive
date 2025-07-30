# module import
from time import sleep

# package import
from PySide6.QtCore import Slot

# local package import
import config
from models.log import get_logger
from models.workers.base import run_wrapper, LongLiveWorker
from sign import livehime_sign


class CoverStateUpdateWorker(LongLiveWorker):
    def __init__(self):
        super().__init__(name="封面审核更新")
        self.logger = get_logger(self.__class__.__name__)

    @Slot()
    @run_wrapper
    def run(self, /) -> None:
        while self.is_running and config.room_info["cover_status"] == 0:
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
            response = config.session.get(url, params=params)
            response.encoding = "utf-8"
            self.logger.info("PreLive Response")
            response = response.json()
            self.logger.info(f"PreLive Result: {response}")
            config.room_info.update({
                "cover_audit_reason": response["data"]["cover"]["auditReason"],
                "cover_url": response["data"]["cover"]["url"],
                "cover_status": response["data"]["cover"]["auditStatus"],
                "title": response["data"]["title"],
            })
            sleep(3)

    @staticmethod
    @Slot()
    def on_finished(parent_window: "StreamConfigPanel"):
        parent_window.cover_audit_state()
