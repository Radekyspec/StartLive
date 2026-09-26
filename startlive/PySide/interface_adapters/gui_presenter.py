from PySide6.QtWidgets import QMessageBox

from startlive.PySide.log import get_logger
from startlive.core.exceptions.WorkerException import WorkerException
from startlive.core.workers.base import Presenter


class GUIPresenter(Presenter):
    def __init__(self, view: "MainWindow"):
        super().__init__()
        self._view = view
        self.logger = get_logger(self.__class__.__name__)

    def prepare_success_view(self, *args, **kwargs): ...

    def prepare_fail_view(self, exception: WorkerException):
        QMessageBox.critical(self._view, f"{exception.name}线程错误",
                             repr(exception.real_exc))

    def prepare_progress_view(self, *args, **kwargs): ...
