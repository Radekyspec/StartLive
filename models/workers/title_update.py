# module import

# package import
from PySide6.QtCore import Slot

# local package import
import config
from exceptions import TitleUpdateError
from sign import livehime_sign
from models.log import get_logger
from models.workers.base import BaseWorker


class TitleUpdateWorker(BaseWorker):
    def __init__(self, parent_window: "StreamConfigPanel", title):
        super().__init__(name="标题更新")
        self.parent_window = parent_window
        self.title = title
        self.logger = get_logger(self.__class__.__name__)

    @Slot()
    def run(self, /) -> None:
        url = "https://api.live.bilibili.com/room/v1/Room/updateV2"
        title_data = {
            "csrf": config.cookies_dict["bili_jct"],
            "csrf_token": config.cookies_dict["bili_jct"],
            "room_id": config.room_info["room_id"],
            "title": self.title,
        }
        self.logger.info(f"updateV2 Request")
        try:
            response = config.session.post(url, params=livehime_sign({}),
                                           data=title_data)
            response.encoding = "utf-8"
            self.logger.info("updateV2 Response")
            response = response.json()
            self.logger.info(f"updateV2 Result: {response}")
            if response["code"] != 0:
                raise TitleUpdateError(response["message"])
        except Exception as e:
            self.exception = e
            self.parent_window.save_title_btn.setEnabled(True)
        finally:
            self.finished = True
