from src.PySide.interface_adapters.cover import CoverStateUpdatePresenter
from src.core.workers.base import Presenter
from src.core.workers.cover import CoverStateUpdateWorker


class CoverUploadPresenter(Presenter):
    def __init__(self, view):
        super().__init__()
        self._view = view

    def prepare_success_view(self, *args, **kwargs):
        self._view.cover_audit_state()
        cover_state_presenter = CoverStateUpdatePresenter(self._view)
        cover_state_updater = CoverStateUpdateWorker(
            on_finished=cover_state_presenter.prepare_success_view
        )
        self._view.parent_window.add_thread(
            cover_state_updater
        )
        if self._view.cover_crop_widget is not None:
            self._view.cover_crop_widget.close()

    def prepare_fail_view(self, *args, **kwargs):
        self._view.cover_crop_widget.btn_upload.setText("保存封面")
        self._view.cover_crop_widget.btn_upload.setEnabled(True)

    def prepare_progress_view(self, *args, **kwargs): ...
