from typing import Optional

from PySide6.QtCore import QObject, QThread, Signal, Slot

from src.PySide.updater.update_worker import VelopackUpdateWorker


class VelopackUpdateController(QObject):
    no_update = Signal()
    update_ready = Signal()
    failed = Signal(str)

    def __init__(self, update_url: str,
                 parent: Optional[QObject] = None) -> None:
        super().__init__(parent)

        self._update_url = update_url

        self._thread: Optional[QThread] = None
        self._worker: Optional[VelopackUpdateWorker] = None

        self._manager = None
        self._update_info = None

    @Slot()
    def start(self) -> None:
        if self._thread is not None:
            return

        thread = QThread(self)
        worker = VelopackUpdateWorker(self._update_url)

        worker.moveToThread(thread)

        thread.started.connect(worker.run)

        worker.no_update.connect(self.no_update)
        worker.failed.connect(self.failed)
        worker.update_downloaded.connect(
            self._on_update_downloaded
        )

        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)

        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._on_thread_finished)

        self._thread = thread
        self._worker = worker

        thread.start()

    @Slot(object, object)
    def _on_update_downloaded(
            self,
            manager,
            update_info,
    ) -> None:
        self._manager = manager
        self._update_info = update_info
        self.update_ready.emit()

    @Slot()
    def _on_thread_finished(self) -> None:
        self._thread = None
        self._worker = None

    @Slot()
    def apply_and_restart(self) -> None:
        if self._manager is None or self._update_info is None:
            return

        # Velopack 将等待当前进程退出、应用更新并重新启动程序。
        self._manager.apply_updates_and_restart(
            self._update_info
        )
