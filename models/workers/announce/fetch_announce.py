# module import
from PySide6.QtCore import Slot

# local package import
import app_state
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

    @Slot()
    def on_finished(self, panel: "StreamConfigPanel"):
        panel.announce_input.setText(app_state.room_info["announcement"])
        panel.announce_input.textEdited.connect(
            lambda: panel.save_announce_btn.setEnabled(True))
        self._session.close()
