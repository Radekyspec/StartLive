# module import
from PySide6.QtCore import Slot
from PySide6.QtGui import QPixmap

# local package import
import config
from models.log import get_logger
from models.workers.base import BaseWorker, run_wrapper


class FetchCoverWorker(BaseWorker):
    def __init__(self):
        super().__init__(name="封面获取")
        self.logger = get_logger(self.__class__.__name__)

    @Slot()
    @run_wrapper
    def run(self, /) -> None:
        url = config.room_info["cover_url"]
        self.logger.info(f"cover data Request")
        response = config.session.get(url)
        self.logger.info("cover data Response")
        config.room_info["cover_data"] = response.content

    @staticmethod
    def on_finished(parent: "CoverCropWidget"):
        pix = QPixmap()
        pix.loadFromData(config.room_info["cover_data"])
        config.room_info["cover_data"] = None
        parent.label.setPixmap(pix)
