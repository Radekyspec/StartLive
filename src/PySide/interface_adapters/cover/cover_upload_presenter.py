from typing import TYPE_CHECKING

from src.core.workers.base import Presenter

if TYPE_CHECKING:
    from src.PySide.window.stream_config import StreamConfigPanel


class CoverUploadPresenter(Presenter):
    def __init__(self, view: "StreamConfigPanel"):
        super().__init__()
        self._view = view

    def prepare_success_view(self, *args, **kwargs):
        self._view.cover_audit_state()
        self._view.ensure_cover_audit_monitor()
        if self._view.cover_crop_widget is not None:
            self._view.cover_crop_widget.close()

    def prepare_fail_view(self, exception: Exception):
        widget = self._view.cover_crop_widget
        if widget is None:
            return
        widget.btn_upload.setText("保存封面")
        widget.btn_upload.setEnabled(True)

    def prepare_progress_view(self, *args, **kwargs): ...
