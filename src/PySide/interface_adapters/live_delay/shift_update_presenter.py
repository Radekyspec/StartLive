from PySide6.QtWidgets import QPushButton

from src.core.workers.base import Presenter


class TimeShiftUpdatePresenter(Presenter):
    def __init__(self, view: QPushButton):
        super().__init__()
        self._view = view

    def prepare_success_view(self, *args, **kwargs): ...

    def prepare_fail_view(self, exception: Exception):
        self._view.setEnabled(True)

    def prepare_progress_view(self, *args, **kwargs): ...
