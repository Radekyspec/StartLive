# module import
from PySide6.QtCore import Slot
from PySide6.QtGui import QPixmap

# local package import
import app_state
from models.log import get_logger
from models.workers.base import BaseWorker, run_wrapper


class FetchCoverWorker(BaseWorker):
    def __init__(self, parent: "CoverCropWidget", /):
        super().__init__(name="封面获取")
        self.parent = parent
        self.logger = get_logger(self.__class__.__name__)

    @Slot()
    @run_wrapper
    def run(self, /) -> None:
        url = app_state.room_info["cover_url"]
        self.logger.info(f"cover data Request")
        response = self._session.get(url)
        self.logger.info("cover data Response")
        app_state.room_info["cover_data"] = response.content

    @Slot()
    def on_finished(self):
        pix = QPixmap()
        pix.loadFromData(app_state.room_info["cover_data"])
        app_state.room_info["cover_data"] = None
        self.parent.label.coverUpdated.emit(pix)
        self._session.close()
