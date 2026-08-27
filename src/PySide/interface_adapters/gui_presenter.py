from typing import TYPE_CHECKING

from PySide6.QtWidgets import QMessageBox

from src.PySide.log import get_logger
from src.core.exceptions.WorkerException import WorkerException
from src.core.workers.base import Presenter

if TYPE_CHECKING:
    from src.PySide.window.main_window import MainWindow


class GUIPresenter(Presenter):
    def __init__(self, view: "MainWindow"):
        super().__init__()
        self._view = view
        self.logger = get_logger(self.__class__.__name__)

    def prepare_success_view(self, *args, **kwargs): ...

    def prepare_fail_view(self, exception: Exception):
        if isinstance(exception, WorkerException):
            message = f"{exception.name}线程错误"
            detail = repr(exception.real_exc)
        else:
            message = "工作线程错误"
            detail = repr(exception)
        QMessageBox.critical(self._view, message, detail)

    def prepare_progress_view(self, *args, **kwargs): ...
