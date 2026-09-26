import os
import unittest
from queue import Empty
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import shiboken6
from PySide6.QtCore import QEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QWidget

from src.PySide.interface_adapters.pre_live.fetch_pre_live_presenter import (
    FetchPreLivePresenter,
)
from src.PySide.states import LoginState
from src.PySide.window.stream_config import StreamConfigPanel
from src.core import app_state
from src.core.constant import CoverStatus


class _Action:
    def __init__(self) -> None:
        self.enabled = True

    def setEnabled(self, enabled: bool) -> None:
        self.enabled = enabled


class _ParentWindow(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.tray_start_live_action = _Action()
        self.tray_stop_live_action = _Action()
        self.threads = []

    def add_thread(self, worker, **_kwargs) -> None:
        self.threads.append(worker)

    def popup_face_widget(self, *_args, **_kwargs) -> None:
        pass


class StreamConfigClipboardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self._obs_client = app_state.obs_client
        self._obs_connecting = app_state.obs_connecting
        self._stream_status = {
            key: app_state.stream_status[key]
            for key in ("live_status", "stream_addr", "stream_key")
        }
        self._room_title = app_state.room_info["title"]
        self._recent_title = list(app_state.room_info["recent_title"])
        self._cover_status = app_state.room_info["cover_status"]
        app_state.obs_client = None
        app_state.obs_connecting = False
        app_state.stream_status["live_status"] = False
        app_state.stream_status["stream_addr"] = None
        app_state.stream_status["stream_key"] = None
        app_state.room_info["title"] = "测试直播"
        app_state.room_info["recent_title"].clear()
        app_state.room_info["cover_status"] = CoverStatus.AUDIT_PASSED
        self._clear_obs_queue()
        self.parent = _ParentWindow()
        self.panel = StreamConfigPanel(self.parent)

    def tearDown(self) -> None:
        if shiboken6.isValid(self.panel):
            self.panel.deleteLater()
        if shiboken6.isValid(self.parent):
            self.parent.deleteLater()
        QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.app.processEvents()
        app_state.obs_client = self._obs_client
        app_state.obs_connecting = self._obs_connecting
        for key, value in self._stream_status.items():
            app_state.stream_status[key] = value
        app_state.room_info["title"] = self._room_title
        app_state.room_info["recent_title"].clear()
        app_state.room_info["recent_title"].extend(self._recent_title)
        app_state.room_info["cover_status"] = self._cover_status
        self._clear_obs_queue()

    @staticmethod
    def _clear_obs_queue() -> None:
        while True:
            try:
                app_state.obs_req_queue.get_nowait()
            except Empty:
                return

    def test_copy_buttons_start_disabled_with_distinct_accessibility_text(self) -> None:
        self.assertFalse(self.panel.copy_addr_btn.isEnabled())
        self.assertFalse(self.panel.copy_key_btn.isEnabled())
        self.assertEqual(self.panel.copy_addr_btn.toolTip(), "复制串流地址")
        self.assertEqual(self.panel.copy_key_btn.toolTip(), "复制串流密钥")
        self.assertEqual(
            self.panel.copy_addr_btn.accessibleName(), "复制串流地址")
        self.assertEqual(
            self.panel.copy_key_btn.accessibleName(), "复制串流密钥")
        self.assertIs(
            self.panel._copy_addr_timer.parent(), self.panel.copy_addr_btn)
        self.assertIs(
            self.panel._copy_key_timer.parent(), self.panel.copy_key_btn)
        self.assertTrue(self.panel._copy_addr_timer.isSingleShot())
        self.assertTrue(self.panel._copy_key_timer.isSingleShot())

    def test_fill_stream_info_populates_and_enables_copy_buttons(self) -> None:
        self.panel.fill_stream_info("rtmp://example.test/live", "secret")

        self.assertEqual(
            self.panel.addr_input.text(), "rtmp://example.test/live")
        self.assertEqual(self.panel.key_input.text(), "secret")
        self.assertTrue(self.panel.copy_addr_btn.isEnabled())
        self.assertTrue(self.panel.copy_key_btn.isEnabled())

    def test_already_live_presenter_uses_display_only_path(self) -> None:
        app_state.obs_client = object()
        app_state.stream_status["live_status"] = True
        app_state.stream_status["stream_addr"] = "rtmp://live.example/live"
        app_state.stream_status["stream_key"] = "existing-secret"
        self.panel.obs_auto_live_checkbox.setChecked(True)
        presenter = FetchPreLivePresenter(self.panel, LoginState())

        with patch.object(
                self.panel, "display_stream_info",
                wraps=self.panel.display_stream_info) as display:
            presenter.prepare_success_view()

        display.assert_called_once_with(
            "rtmp://live.example/live", "existing-secret")
        self.assertTrue(self.panel.copy_addr_btn.isEnabled())
        self.assertTrue(self.panel.copy_key_btn.isEnabled())
        self.assertTrue(app_state.obs_req_queue.empty())

    def test_copy_feedback_resets_after_real_timer_interval(self) -> None:
        self.assertEqual(self.panel._COPY_FEEDBACK_MS, 1500)
        self.panel.fill_stream_info("rtmp://example.test/live", "secret")

        self.panel.copy_key_btn.click()

        self.assertEqual(QApplication.clipboard().text(), "secret")
        self.assertEqual(self.panel.copy_key_btn.text(), "已复制")
        self.assertEqual(
            self.panel.copy_key_btn.toolTip(), "串流密钥已复制到剪贴板")
        QTest.qWait(1650)
        self.app.processEvents()
        self.assertEqual(self.panel.copy_key_btn.text(), "复制")
        self.assertEqual(self.panel.copy_key_btn.toolTip(), "复制串流密钥")

    def test_repeated_copy_restarts_feedback_timer(self) -> None:
        self.panel.fill_stream_info("rtmp://example.test/live", "secret")

        with patch.object(StreamConfigPanel, "_COPY_FEEDBACK_MS", 200):
            self.panel.copy_addr_btn.click()
            QTest.qWait(140)
            self.panel.copy_addr_btn.click()
            QTest.qWait(120)
            self.app.processEvents()
            self.assertEqual(self.panel.copy_addr_btn.text(), "已复制")

            QTest.qWait(100)
            self.app.processEvents()
            self.assertEqual(self.panel.copy_addr_btn.text(), "复制")

    def test_stop_immediately_clears_copy_controls_and_feedback(self) -> None:
        self.panel.fill_stream_info("rtmp://example.test/live", "secret")
        self.panel.copy_addr_btn.click()
        self.panel.copy_key_btn.click()
        self.panel.stop_btn.setEnabled(True)

        self.panel._stop_live()

        self.assertEqual(self.panel.addr_input.text(), "")
        self.assertEqual(self.panel.key_input.text(), "")
        self.assertFalse(self.panel.copy_addr_btn.isEnabled())
        self.assertFalse(self.panel.copy_key_btn.isEnabled())
        self.assertEqual(self.panel.copy_addr_btn.text(), "复制")
        self.assertEqual(self.panel.copy_key_btn.text(), "复制")
        self.assertFalse(self.panel._copy_addr_timer.isActive())
        self.assertFalse(self.panel._copy_key_timer.isActive())

    def test_panel_deletion_destroys_active_copy_timer(self) -> None:
        self.panel.fill_stream_info("rtmp://example.test/live", "secret")
        timer = self.panel._copy_addr_timer
        self.panel.copy_addr_btn.click()
        self.assertTrue(timer.isActive())

        self.panel.deleteLater()
        QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.app.processEvents()

        self.assertFalse(shiboken6.isValid(self.panel))
        self.assertFalse(shiboken6.isValid(timer))


if __name__ == "__main__":
    unittest.main()
