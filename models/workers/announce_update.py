# module import

# package import
from PySide6.QtCore import Slot

# local package import
import config
from exceptions import AnnounceUpdateError
from models.log import get_logger
from models.workers.base import BaseWorker, run_wrapper
from sign import livehime_sign, order_payload


class AnnounceUpdateWorker(BaseWorker):
    def __init__(self, content: str):
        super().__init__(name="主播公告更新")
        self.content = content
        self.logger = get_logger(self.__class__.__name__)

    @Slot()
    @run_wrapper
    def run(self, /) -> None:
        url = "https://api.live.bilibili.com/xlive/app-blink/v1/room/AnnounceCommit"
        announce_data = livehime_sign({})
        announce_data.update(
            {
                "content": self.content,
                "csrf_token": config.cookies_dict["bili_jct"],
                "csrf": config.cookies_dict["bili_jct"],
                "type": "1",
            }
        )
        announce_data = order_payload(announce_data)
        self.logger.info(f"AnnounceCommit Request")
        response = config.session.post(url, data=announce_data)
        response.encoding = "utf-8"
        self.logger.info("AnnounceCommit Response")
        # print(response.text)
        response.raise_for_status()
        response = response.json()
        self.logger.info(f"AnnounceCommit Result: {response}")
        if response["code"] != 0:
            raise AnnounceUpdateError(response["message"])
        config.room_info["announcement"] = self.content

    @staticmethod
    @Slot()
    def on_exception(parent_window: "StreamConfigPanel", *args, **kwargs):
        parent_window.save_announce_btn.setEnabled(True)
