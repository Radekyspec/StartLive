# package import
from typing import Callable

# local package import
from src.core import app_state
from src.core.cache import get_cache_path
from src.core.constant import CacheType
from src.core.log import get_logger
from src.core.workers.base import BaseWorker, Presenter


class LoadRecentTitleWorker(BaseWorker):
    def __init__(self, presenter: Presenter, /):
        super().__init__(name="加载最近标题", with_session=False,
                         presenter=presenter)
        self.logger = get_logger(self.__class__.__name__)

    def run(self, report_progress: Callable | None, *args, **kwargs):
        _, _title_file = get_cache_path(
            CacheType.CONFIG,
            f"title{app_state.cookies_dict["DedeUserID"]}")
        if not _title_file.exists():
            return []
        with open(_title_file, "r", encoding="utf-8") as f:
            self.logger.info(f"Load recent title from {str(_title_file)}")
            return list(map(str.strip, f.readlines()))
