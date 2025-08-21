# module import
from PySide6.QtCore import Slot

# local package import
import config
from models.log import get_logger
from models.workers.base import BaseWorker, run_wrapper
from sign import livehime_sign


class FetchAnnounceWorker(BaseWorker):
    def __init__(self):
        super().__init__(name="主播公告获取")
        self.logger = get_logger(self.__class__.__name__)

    @Slot()
    @run_wrapper
    def run(self, /) -> None:
        url = "https://api.live.bilibili.com/xlive/app-blink/v1/room/AnnounceInfo"
        self.logger.info(f"Announcement info Request")
        params = livehime_sign({})
        response = config.session.get(url, params=params)
        response.encoding = "utf-8"
        self.logger.info("Announcement info Response")
        response = response.json()
        config.room_info["announcement"] = response["data"]["announces"]["1"][
            "content"]
        config.scan_status["announce_updated"] = True

    @staticmethod
    @Slot()
    def on_finished(panel: "StreamConfigPanel"):
        panel.announce_input.setText(config.room_info["announcement"])
        panel.announce_input.textEdited.connect(
            lambda: panel.save_announce_btn.setEnabled(True))
