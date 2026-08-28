from typing import TYPE_CHECKING

from PySide6.QtGui import QPixmap

from src.core import app_state
from src.core.workers.base import Presenter

if TYPE_CHECKING:
    from src.PySide.window.cover_crop import CoverCropWidget


class FetchCoverPresenter(Presenter):
    def __init__(self, view: "CoverCropWidget") -> None:
        super().__init__()
        self._view = view

    def prepare_success_view(self) -> None:
        pix = QPixmap()
        pix.loadFromData(app_state.room_info["cover_data"])
        app_state.room_info["cover_data"] = None
        self._view.label.coverUpdated.emit(pix)

    def prepare_fail_view(self, exception: Exception) -> None: ...

    def prepare_progress_view(self, *args, **kwargs) -> None: ...
