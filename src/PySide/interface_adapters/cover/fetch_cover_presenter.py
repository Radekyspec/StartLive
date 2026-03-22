from PySide6.QtGui import QPixmap

from src.core import app_state
from src.core.workers.base import Presenter


class FetchCoverPresenter(Presenter):
    def __init__(self, _view):
        super().__init__()
        self._view = _view

    def prepare_success_view(self):
        pix = QPixmap()
        pix.loadFromData(app_state.room_info["cover_data"])
        app_state.room_info["cover_data"] = None
        self._view.label.coverUpdated.emit(pix)

    def prepare_fail_view(self): ...

    def prepare_progress_view(self, *args, **kwargs): ...
