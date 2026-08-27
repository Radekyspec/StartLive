from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from .gui_dispatcher import GUIDispatcher

if TYPE_CHECKING:
    from src.core.workers.base import BaseWorker, LongLiveWorker
    from src.PySide.window.stream_config import StreamConfigPanel


class MainWindowView(Protocol):
    """UI operations presenters require from the main window."""

    def require_panel(self) -> StreamConfigPanel: ...

    def add_thread(
        self,
        worker: BaseWorker | LongLiveWorker,
        /,
        on_progress: bool = False,
    ) -> None: ...

    def update_qr_image(self, qr_url: str) -> None: ...


__all__ = ["GUIDispatcher", "MainWindowView"]
