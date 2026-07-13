from PySide6.QtGui import QIntValidator
from PySide6.QtWidgets import QLineEdit

from src.core.workers.base import Presenter


class FetchTimeShiftPresenter(Presenter):
    def __init__(self, view: QLineEdit):
        super().__init__()
        self._view = view

    def prepare_success_view(self, time_shift: int = 0, min_shift: int = 10,
                             max_shift: int = 300):
        self._view.setValidator(QIntValidator(min_shift, max_shift, self._view))
        self._view.setText(str(time_shift))

    def prepare_fail_view(self, exception: Exception): ...

    def prepare_progress_view(self, *args, **kwargs): ...
