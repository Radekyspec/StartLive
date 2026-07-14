from PySide6.QtCore import QObject, Signal, Slot
from velopack import UpdateManager

from src.PySide.log import get_logger


class VelopackUpdateWorker(QObject):
    no_update = Signal()
    update_downloaded = Signal(object, object)
    failed = Signal(str)
    finished = Signal()

    def __init__(self, update_url: str) -> None:
        super().__init__()
        self._update_url = update_url
        self.logger = get_logger(self.__class__.__name__)

    @Slot()
    def run(self) -> None:
        try:
            manager = UpdateManager(self._update_url)
            update_info = manager.check_for_updates()
            if update_info is None:
                self.no_update.emit()
                return

            # 此操作可能耗时，因此放在后台线程。
            manager.download_updates(update_info)
            self.update_downloaded.emit(manager, update_info)
        except Exception as exc:
            self.logger.exception("Velopack update failed")
            self.failed.emit(str(exc))
        finally:
            self.finished.emit()
