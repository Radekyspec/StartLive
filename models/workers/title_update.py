# module import

# package import
from PySide6.QtCore import Slot

# local package import
import config
from .base import BaseWorker
from sign import livehime_sign


class TitleUpdateWorker(BaseWorker):
    def __init__(self, parent_window: "StreamConfigPanel", title):
        super().__init__(name="标题更新")
        self.parent_window = parent_window
        self.title = title

    @Slot()
    def run(self, /) -> None:
        url = "https://api.live.bilibili.com/room/v1/Room/updateV2"
        title_data = {
            "csrf": config.cookies_dict["bili_jct"],
            "csrf_token": config.cookies_dict["bili_jct"],
            "room_id": config.room_info["room_id"],
            "title": self.title,
        }
        try:
            response = config.session.post(url, params=livehime_sign({}),
                                           data=title_data).json()
            if response["code"] != 0:
                raise ValueError(response["message"])
        except Exception as e:
            self.exception = e
            self.parent_window.save_title_btn.setEnabled(True)
        finally:
            self.finished = True
