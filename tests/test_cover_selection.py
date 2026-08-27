import os
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication, QWidget

from src.PySide.interface_adapters.cover import (
    CoverStateUpdatePresenter,
    CoverUploadPresenter,
)
from src.PySide.window.stream_config import StreamConfigPanel
from src.core import app_state
from src.core.constant import CoverStatus


class _Action:
    def setEnabled(self, _enabled: bool) -> None:
        pass


class _ParentWindow(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.tray_start_live_action = _Action()
        self.tray_stop_live_action = _Action()
        self.workers = []

    def add_thread(self, worker, **_kwargs) -> None:
        self.workers.append(worker)

    def popup_face_widget(self, *_args, **_kwargs) -> None:
        pass


class CoverSelectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.previous_status = app_state.room_info["cover_status"]
        app_state.room_info["cover_status"] = CoverStatus.AUDIT_IN_PROGRESS
        self.parent = _ParentWindow()
        self.panel = StreamConfigPanel(self.parent)

    def tearDown(self) -> None:
        widget = self.panel.cover_crop_widget
        if widget is not None:
            widget.close()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.panel.close()
        self.parent.close()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app_state.room_info["cover_status"] = self.previous_status

    def test_cover_editor_opens_during_audit_and_cleans_up_on_destroy(self) -> None:
        with patch(
            "src.PySide.window.stream_config.FetchCoverWorker"
        ) as worker_type:
            self.panel._edit_cover()

        widget = self.panel.cover_crop_widget
        if widget is None:
            self.fail("cover editor was not created")
        self.assertFalse(self.panel.cover_edit_btn.isEnabled())
        self.assertEqual(self.parent.workers, [worker_type.return_value])

        widget.close()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

        self.assertIsNone(self.panel.cover_crop_widget)
        self.assertTrue(self.panel.cover_edit_btn.isEnabled())

    def test_successful_replacement_reuses_existing_audit_monitor(self) -> None:
        crop_widget = Mock()
        self.panel.cover_crop_widget = crop_widget

        with patch(
            "src.PySide.window.stream_config.CoverStateUpdateWorker"
        ) as worker_type:
            self.panel.ensure_cover_audit_monitor()
            CoverUploadPresenter(self.panel).prepare_success_view()

        worker_type.assert_called_once()
        self.assertEqual(self.parent.workers, [worker_type.return_value])
        crop_widget.close.assert_called_once_with()
        self.panel.cover_crop_widget = None

    def test_monitor_completion_and_failure_allow_later_monitors(self) -> None:
        presenter = CoverStateUpdatePresenter(self.panel)

        with patch(
            "src.PySide.window.stream_config.CoverStateUpdateWorker"
        ) as worker_type:
            self.panel.ensure_cover_audit_monitor()
            app_state.room_info["cover_status"] = CoverStatus.AUDIT_PASSED
            presenter.prepare_success_view()

            app_state.room_info["cover_status"] = CoverStatus.AUDIT_IN_PROGRESS
            self.panel.ensure_cover_audit_monitor()
            presenter.prepare_fail_view(RuntimeError("monitor failed"))

            self.panel.ensure_cover_audit_monitor()

        self.assertEqual(worker_type.call_count, 3)
        self.assertEqual(len(self.parent.workers), 3)
        self.assertTrue(self.panel._cover_audit_monitor_active)


if __name__ == "__main__":
    unittest.main()
