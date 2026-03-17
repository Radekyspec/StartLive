from src.core import app_state
from src.core.workers.base import Presenter


class AreaUpdatePresenter(Presenter):
    def __init__(self, view) -> None:
        self._view = view

    def prepare_success_view(self, area: str):
        app_state.room_info[
            "parent_area"] = app_state.area_reverse[area]
        app_state.room_info[
            "area"] = area
        app_state.room_info["area_code"] = app_state.area_codes[area]
        self._view.parent_combo.setCurrentText(
            app_state.room_info["parent_area"])
        self._view.child_combo.setCurrentText(app_state.room_info["area"])

    def prepare_fail_view(self):
        enabled = self._view.enable_child_combo_autosave(False)
        self._view.parent_combo.setCurrentText(
            app_state.room_info["parent_area"])
        self._view.child_combo.setCurrentText(app_state.room_info["area"])
        self._view.enable_child_combo_autosave(enabled)
        self._view.modify_area_btn.setEnabled(True)
