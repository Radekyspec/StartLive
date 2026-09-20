from src.core.workers.base import Presenter


class StopLivePresenter(Presenter):
    def __init__(self, view: "StreamConfigPanel"):
        super().__init__()
        self._view = view

    def prepare_success_view(self, *args, **kwargs): ...

    def prepare_fail_view(self, exception: Exception):
        self._view.start_btn.setEnabled(False)
        self._view.parent_window.tray_start_live_action.setEnabled(
            False)
        self._view.stop_btn.setEnabled(True)
        self._view.parent_window.tray_stop_live_action.setEnabled(True)
        self._view.modify_area_btn.setEnabled(True)

    def prepare_progress_view(self, *args, **kwargs): ...
