import os
import re
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication, QLabel, QWidget

from src.core import app_state
from src.core.constant import (
    DARK_COVER_CSS,
    DARK_CSS,
    DARK_MODERN_CSS,
    LIGHT_COVER_CSS,
    LIGHT_CSS,
    LIGHT_MODERN_CSS,
    CoverStatus,
)
from src.PySide.widgets.side_bar_frame import SideBar
from src.PySide.window.stream_config import StreamConfigPanel


class _Action:
    def setEnabled(self, _enabled: bool) -> None:
        pass


class _ParentWindow(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.tray_start_live_action = _Action()
        self.tray_stop_live_action = _Action()

    def add_thread(self, *_args, **_kwargs) -> None:
        pass

    def popup_face_widget(self, *_args, **_kwargs) -> None:
        pass


def _contrast_ratio(foreground: str, background: str) -> float:
    def luminance(color: str) -> float:
        channels = [int(color[index:index + 2], 16) / 255
                    for index in (1, 3, 5)]
        linear = [channel / 12.92 if channel <= 0.04045 else
                  ((channel + 0.055) / 1.055) ** 2.4
                  for channel in channels]
        return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]

    lighter, darker = sorted(
        (luminance(foreground), luminance(background)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


class ModernUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        app_state.obs_client = None
        app_state.obs_op = False
        app_state.obs_connecting = False

    def _make_panel(self) -> tuple[_ParentWindow, StreamConfigPanel]:
        parent = _ParentWindow()
        panel = StreamConfigPanel(parent)
        return parent, panel

    def _dispose(self, *widgets: QWidget) -> None:
        for widget in widgets:
            widget.close()
            widget.deleteLater()
        self.app.processEvents()

    def test_normal_and_cover_themes_share_the_modern_suffix(self) -> None:
        theme_pairs = (
            (DARK_CSS, DARK_MODERN_CSS),
            (DARK_COVER_CSS, DARK_MODERN_CSS),
            (LIGHT_CSS, LIGHT_MODERN_CSS),
            (LIGHT_COVER_CSS, LIGHT_MODERN_CSS),
        )
        for stylesheet, suffix in theme_pairs:
            with self.subTest(suffix=suffix.splitlines()[0]):
                self.assertTrue(stylesheet.endswith(suffix))
                self.assertIn("QGroupBox#SectionCard", stylesheet)
                self.assertIn("QLabel#PageTitle", stylesheet)
                self.assertIn("QFrame#SideBar", stylesheet)

    def test_action_focus_selectors_are_visible_and_appended_last(self) -> None:
        selectors = (
            "QPushButton#PrimaryAction:focus",
            "QPushButton#DangerAction:focus",
            "QPushButton#GhostAction:focus, QPushButton#SecondaryAction:focus",
            "QToolButton#MenuButton:focus",
        )
        for stylesheet in (
                DARK_CSS, DARK_COVER_CSS, LIGHT_CSS, LIGHT_COVER_CSS):
            for selector in selectors:
                self.assertIn(selector, stylesheet)
            self.assertGreater(
                stylesheet.rfind("QPushButton#PrimaryAction:focus"),
                stylesheet.rfind("QMenuBar::item"),
            )

        parent, panel = self._make_panel()
        parent.resize(610, 470)
        panel.setGeometry(parent.rect())
        parent.show()
        panel.show()
        parent.activateWindow()
        for button in (panel.start_btn, panel.stop_btn,
                       panel.copy_addr_btn, panel.connect_btn):
            button.setEnabled(True)
            button.setFocus()
            self.app.processEvents()
            self.assertTrue(button.hasFocus(), button.objectName())
        self._dispose(panel, parent)

    def test_primary_background_meets_white_text_contrast(self) -> None:
        for suffix in (DARK_MODERN_CSS, LIGHT_MODERN_CSS):
            rule = re.search(
                r"QPushButton#PrimaryAction \{.*?background-color: "
                r"(#[0-9a-fA-F]{6});",
                suffix,
                re.DOTALL,
            )
            self.assertIsNotNone(rule)
            assert rule is not None
            self.assertGreaterEqual(_contrast_ratio("#ffffff", rule.group(1)),
                                    4.5)

    def test_stream_panel_preserves_public_controls_and_accessible_names(self) -> None:
        parent, panel = self._make_panel()

        self.assertEqual(panel.objectName(), "StreamConfigPanel")
        self.assertIsNotNone(panel.findChild(QLabel, "PageTitle"))
        self.assertIsNotNone(panel.findChild(QLabel, "PageSubtitle"))
        self.assertEqual(panel.start_btn.objectName(), "PrimaryAction")
        self.assertEqual(panel.stop_btn.objectName(), "DangerAction")
        self.assertEqual(panel.addr_input.accessibleName(), "串流地址")
        self.assertEqual(panel.key_input.accessibleName(), "串流密钥")
        self.assertEqual(panel.copy_addr_btn.accessibleName(), "复制串流地址")
        self.assertEqual(panel.copy_key_btn.accessibleName(), "复制串流密钥")
        self.assertNotEqual(panel.copy_addr_btn.accessibleName(),
                            panel.copy_key_btn.accessibleName())

        labels = {label.text(): label for label in panel.findChildren(QLabel)}
        expected_buddies = {
            "服务器 IP:": panel.host_input,
            "端口:": panel.port_input,
            "服务器密码:": panel.pass_input,
            "串流地址:": panel.addr_input,
            "串流密钥:": panel.key_input,
            "房间标题:": panel.title_input,
            "主播公告:": panel.announce_input,
            "分区选择:": panel.parent_combo,
            "直播封面:": panel.cover_edit_btn,
        }
        for text, buddy in expected_buddies.items():
            with self.subTest(label=text):
                self.assertIs(labels[text].buddy(), buddy)
                self.assertTrue(buddy.accessibleName())

        self._dispose(panel, parent)

    def test_cover_status_uses_semantic_property_without_inline_color(self) -> None:
        parent, panel = self._make_panel()
        old_status = app_state.room_info["cover_status"]
        old_reason = app_state.room_info["cover_audit_reason"]
        try:
            cases = (
                (CoverStatus.AUDIT_PASSED, "success"),
                (CoverStatus.AUDIT_IN_PROGRESS, "warning"),
                (CoverStatus.AUDIT_FAILED, "error"),
            )
            for cover_status, property_value in cases:
                app_state.room_info["cover_status"] = cover_status
                app_state.room_info["cover_audit_reason"] = "尺寸不符合要求"
                panel.cover_audit_state()
                self.assertEqual(panel.cover_status.property("status"),
                                 property_value)
                self.assertEqual(panel.cover_status.styleSheet(), "")
        finally:
            app_state.room_info["cover_status"] = old_status
            app_state.room_info["cover_audit_reason"] = old_reason
            self._dispose(panel, parent)

    def test_large_font_panel_scrolls_without_growing_its_minimum_size(self) -> None:
        parent, panel = self._make_panel()
        font = QFont(panel.font())
        font.setPointSize(18)
        panel.setFont(font)
        panel.resize(480, 300)
        panel.show()
        self.app.processEvents()

        self.assertTrue(panel.scroll_area.widgetResizable())
        self.assertIs(panel.scroll_area.widget(), panel._scroll_content)
        self.assertEqual(panel.width(), 480)
        self.assertEqual(panel.height(), 300)
        self.assertLess(panel.minimumSizeHint().height(),
                        panel._scroll_content.minimumSizeHint().height())
        self.assertGreater(panel.scroll_area.verticalScrollBar().maximum(), 0)
        self.assertEqual(panel.scroll_area.horizontalScrollBar().maximum(), 0)

        self._dispose(panel, parent)

    def test_sidebar_width_and_toggle_accessibility_follow_font_metrics(self) -> None:
        parent = _ParentWindow()
        sidebar = SideBar(
            parent,
            icon_path=Path("resources"),
            expanded_width=80,
            collapsed_width=58,
        )
        font = QFont(sidebar.font())
        font.setPointSize(20)
        sidebar.setFont(font)

        self.assertEqual(sidebar.toggle_btn.accessibleName(), "展开侧边栏")
        self.assertFalse(sidebar.toggle_btn.property("expanded"))
        hinted_width = sidebar.expanded_width_hint()
        self.assertGreater(hinted_width, 80)

        sidebar._toggle()
        self.assertEqual(sidebar.toggle_btn.accessibleName(), "收起侧边栏")
        self.assertTrue(sidebar.toggle_btn.property("expanded"))
        self.assertGreaterEqual(sidebar._expanded_width, hinted_width)
        self.assertEqual(sidebar._anim.endValue(), sidebar._expanded_width)
        sidebar._anim.stop()

        self.assertEqual(sidebar.btn_theme.toolTip(), "切换主题")
        self.assertEqual(sidebar.btn_home.accessibleName(), "主界面")
        self.assertEqual(sidebar.btn_settings.accessibleName(), "设置")
        self._dispose(sidebar, parent)


if __name__ == "__main__":
    unittest.main()
