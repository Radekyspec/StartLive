from typing import TYPE_CHECKING

from src.core.workers.base import Presenter

if TYPE_CHECKING:
    from src.PySide.window.stream_config import StreamConfigPanel


class CoverStateUpdatePresenter(Presenter):
    def __init__(self, view: "StreamConfigPanel") -> None:
        super().__init__()
        self._view = view

    def prepare_success_view(self) -> None:
        try:
            self._view.cover_audit_state()
        finally:
            self._view.finish_cover_audit_monitor()

    def prepare_fail_view(self, exception: Exception) -> None:
        self._view.finish_cover_audit_monitor()

    def prepare_progress_view(self, *args, **kwargs) -> None: ...
