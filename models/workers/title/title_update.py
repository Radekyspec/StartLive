# package import
from PySide6.QtCore import Slot

# local package import
import app_state
from constant import CacheType, MAX_RECENT_TITLE
from exceptions import TitleUpdateError
from models.cache import get_cache_path
from models.log import get_logger
from models.workers.base import BaseWorker, run_wrapper
from sign import livehime_sign


class TitleUpdateWorker(BaseWorker):
    def __init__(self, parent: "StreamConfigPanel", /, title):
        super().__init__(name="标题更新")
        self.parent = parent
        self.title = title
        self.logger = get_logger(self.__class__.__name__)

    @Slot()
    @run_wrapper
    def run(self, /) -> None:
        url = "https://api.live.bilibili.com/xlive/app-blink/v1/preLive/UpdatePreLiveInfo"
        title_data = {
            "csrf": app_state.cookies_dict["bili_jct"],
            "csrf_token": app_state.cookies_dict["bili_jct"],
            "mobi_app": "pc_link",
            "room_id": app_state.room_info["room_id"],
            "title": self.title,
        }
        self.logger.info(f"updateV2 Request")
        response = self._session.post(url, params=livehime_sign({}),
                                      data=title_data)
        response.encoding = "utf-8"
        self.logger.info("updateV2 Response")
        response = response.json()
        self.logger.info(f"updateV2 Result: {response}")
        if response["code"] != 0:
            raise TitleUpdateError(response["message"])
        print(response)
        self.title = response["data"]["audit_info"]["audit_title"]
        app_state.room_info["title"] = self.title
        if self.title in app_state.room_info["recent_title"]:
            app_state.room_info["recent_title"].remove(self.title)
        app_state.room_info["recent_title"].insert(0, self.title)
        _, _title_file = get_cache_path(
            CacheType.CONFIG,
            f"title{app_state.cookies_dict["DedeUserID"]}")
        with open(_title_file, "w", encoding="utf-8") as f:
            f.write("\n".join(
                app_state.room_info["recent_title"][:MAX_RECENT_TITLE]))

    @Slot()
    def on_exception(self, *args, **kwargs):
        self.parent.save_title_btn.setEnabled(True)

    @Slot()
    def on_finished(self, *args, **kwargs):
        self._session.close()
        self.parent.title_input.clear()
        self.parent.title_input.addItems(app_state.room_info["recent_title"])
