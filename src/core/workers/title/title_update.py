# package import
from typing import Callable

# local package import
from src.core import app_state
from src.core.cache import get_cache_path
from src.core.constant import CacheType, MAX_RECENT_TITLE
from src.core.exceptions import TitleUpdateError
from src.core.log import get_logger
from src.core.sign import livehime_sign
from src.core.workers.base import BaseWorker, Presenter


class TitleUpdateWorker(BaseWorker):
    def __init__(self, presenter: Presenter, /, title):
        super().__init__(name="标题更新", presenter=presenter)
        self._title = title
        self.logger = get_logger(self.__class__.__name__)

    def run(self, report_progress: Callable | None, *args, **kwargs):
        url = "https://api.live.bilibili.com/xlive/app-blink/v1/preLive/UpdatePreLiveInfo"
        title_data = {
            "csrf": app_state.cookies_dict["bili_jct"],
            "csrf_token": app_state.cookies_dict["bili_jct"],
            "mobi_app": "pc_link",
            "room_id": app_state.room_info["room_id"],
            "title": self._title,
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
        new_title = response["data"]["audit_info"]["audit_title"]
        app_state.room_info["title"] = new_title if new_title else self._title
        if self._title in app_state.room_info["recent_title"]:
            app_state.room_info["recent_title"].remove(self._title)
        app_state.room_info["recent_title"].insert(0, self._title)
        _, _title_file = get_cache_path(
            CacheType.CONFIG,
            f"title{app_state.cookies_dict["DedeUserID"]}")
        with open(_title_file, "w", encoding="utf-8") as f:
            f.write("\n".join(
                app_state.room_info["recent_title"][:MAX_RECENT_TITLE]))
