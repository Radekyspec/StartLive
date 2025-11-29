# package import

from PySide6.QtCore import Slot

# local package import
import app_state
from constant import CacheType
from models.cache import get_cache_path
from models.log import get_logger
from models.workers.base import BaseWorker, run_wrapper


class LoadRecentTitleWorker(BaseWorker):
    def __init__(self, parent: "StreamConfigPanel", /):
        super().__init__(name="加载最近标题", with_session=False)
        self.parent = parent
        self.logger = get_logger(self.__class__.__name__)
        self.title = []

    @Slot()
    @run_wrapper
    def run(self, /) -> None:
        _, _title_file = get_cache_path(
            CacheType.CONFIG,
            f"title{app_state.cookies_dict["DedeUserID"]}")
        if not _title_file.exists():
            return
        with open(_title_file, "r", encoding="utf-8") as f:
            self.logger.info(f"Load recent title from {str(_title_file)}")
            self.title = list(map(str.strip, f.readlines()))

    @Slot()
    def on_finished(self, *args, **kwargs):
        for title in self.title:
            if title in app_state.room_info["recent_title"]:
                continue
            app_state.room_info["recent_title"].append(title)
        self.parent.title_input.clear()
        self.parent.title_input.addItems(app_state.room_info["recent_title"])
