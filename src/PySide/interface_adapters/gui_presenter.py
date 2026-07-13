from PySide6.QtWidgets import QMessageBox

from src.PySide.log import get_logger
from src.core.exceptions.WorkerException import WorkerException
from src.core.workers.base import Presenter


class GUIPresenter(Presenter):
    def __init__(self, view: "MainWindow"):
        super().__init__()
        self._view = view
        self.logger = get_logger(self.__class__.__name__)

    def prepare_success_view(self, *args, **kwargs): ...

    def prepare_fail_view(self, exception: WorkerException):
        self.logger.error(exception.real_exc)
        QMessageBox.critical(self._view, f"{exception.name}线程错误",
                             repr(exception.real_exc))

    def prepare_progress_view(self, *args, **kwargs): ...
