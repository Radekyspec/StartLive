# module import
from typing import Callable

# local package import
from src.core import app_state
from src.core.log import get_logger
from src.core.workers.base import BaseWorker, Presenter


class FetchCoverWorker(BaseWorker):
    def __init__(self, presenter: Presenter):
        super().__init__(name="封面获取", presenter=presenter)
        self.logger = get_logger(self.__class__.__name__)

    def run(self, report_progress: Callable | None, *args, **kwargs):
        url = app_state.room_info["cover_url"]
        self.logger.info(f"cover data Request")
        response = self._session.get(url)
        self.logger.info("cover data Response")
        app_state.room_info["cover_data"] = response.content
