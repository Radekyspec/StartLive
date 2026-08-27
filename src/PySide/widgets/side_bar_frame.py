from pathlib import Path

from PySide6.QtCore import QEasingCurve, QSize, Qt, QVariantAnimation, Slot
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QFrame, QSizePolicy, QToolButton, QVBoxLayout


class SideBar(QFrame):
    def __init__(self, parent=None, *, icon_path: Path, expanded_width: int,
                 collapsed_width: int):
        super().__init__(parent)
        self._requested_expanded_width = expanded_width
        self._expanded_width = expanded_width
        self._collapsed_width = collapsed_width
        self._icon_path = icon_path
        self._expanded = False
        self._anim_changing = False
        self.setObjectName("SideBar")
        self.setFixedWidth(self._collapsed_width)
        self._light_icons = [
            QIcon(str(icon_path / "light-menu.svg")),
            QIcon(str(icon_path / "light-theme.svg")),
            QIcon(str(icon_path / "light-home.svg")),
            QIcon(str(icon_path / "light-log.svg")),
            QIcon(str(icon_path / "light-settings.svg")),
        ]
        self._dark_icons = [
            QIcon(str(icon_path / "dark-menu.svg")),
            QIcon(str(icon_path / "dark-theme.svg")),
            QIcon(str(icon_path / "dark-home.svg")),
            QIcon(str(icon_path / "dark-log.svg")),
            QIcon(str(icon_path / "dark-settings.svg")),
        ]

        self.toggle_btn = self._make_button(" 菜单", 0, checkable=False)
        self.toggle_btn.clicked.connect(self._toggle)

        self.btn_theme = self._make_button(
            "", 1, checkable=False, tooltip="切换主题")
        self.btn_home = self._make_button(" 主界面", 2)
        self.btn_log = self._make_button(" 日志", 3)
        self.btn_settings = self._make_button(" 设置", 4)

        self._layout = QVBoxLayout(self)
        v = self._layout
        v.setContentsMargins(6, 6, 6, 6)
        v.addWidget(self.toggle_btn)
        v.addSpacing(6)
        v.addWidget(self.btn_theme)
        v.addWidget(self.btn_home)
        v.addStretch(1)
        v.addWidget(self.btn_log)
        v.addWidget(self.btn_settings)

        self._anim = QVariantAnimation(self, duration=200)
        self._anim.valueChanged.connect(self._on_anim_value)
        self._anim.finished.connect(self._on_anim_finished)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._menu_buttons = [
            self.toggle_btn, self.btn_theme, self.btn_home, self.btn_log,
            self.btn_settings
        ]
        self._expanded_width = max(
            self._requested_expanded_width, self.expanded_width_hint())
        self._update_toggle_accessibility()

    def _make_button(self, text: str, icon_index: int, *,
                     checkable: bool = True,
                     tooltip: str | None = None) -> QToolButton:
        button = QToolButton()
        label = tooltip or text.strip()
        button.setProperty("_fulltext", text)
        button.setToolTip(label)
        button.setAccessibleName(label)
        button.setText("" if not self._expanded else text)
        button.setIcon(self._light_icons[icon_index])
        button.setIconSize(QSize(20, 20))
        button.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonIconOnly if not self._expanded
            else Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        )
        button.setCheckable(checkable)
        button.setMinimumHeight(40)
        button.setObjectName("MenuButton")
        button.setSizePolicy(QSizePolicy.Policy.Expanding,
                             QSizePolicy.Policy.Preferred)
        return button

    def expanded_width_hint(self) -> int:
        collapsed = not self._expanded
        if collapsed:
            self._apply_collapsed_ui(False)
        margins = self._layout.contentsMargins()
        width = (max(button.sizeHint().width()
                     for button in self._menu_buttons)
                 + margins.left() + margins.right())
        if collapsed:
            self._apply_collapsed_ui(True)
        return width

    def _update_toggle_accessibility(self) -> None:
        if self._expanded:
            name = "收起侧边栏"
            state = "侧边栏当前已展开"
        else:
            name = "展开侧边栏"
            state = "侧边栏当前已折叠"
        self.toggle_btn.setAccessibleName(name)
        self.toggle_btn.setAccessibleDescription(state)
        self.toggle_btn.setToolTip(name)
        self.toggle_btn.setProperty("expanded", self._expanded)

    @Slot()
    def _on_anim_finished(self):
        self._anim_changing = False

    @Slot()
    def _on_anim_value(self, val):
        try:
            width = int(val)
        except (TypeError, ValueError, OverflowError):
            return
        self.setFixedWidth(width)
        self.updateGeometry()
        parent = self.parentWidget()
        if parent is not None:
            parent.updateGeometry()

    def _apply_collapsed_ui(self, collapsed: bool):
        for b in self._menu_buttons:
            full = b.property("_fulltext")
            b.setText("" if collapsed else full)
            b.setToolButtonStyle(
                Qt.ToolButtonStyle.ToolButtonIconOnly if collapsed else Qt.ToolButtonStyle.ToolButtonTextBesideIcon)

    @Slot()
    def _toggle(self):
        if self._anim_changing:
            return
        self._anim_changing = True
        self._expanded = not self._expanded
        self._update_toggle_accessibility()
        start = self.width()
        if self._expanded:
            self._apply_collapsed_ui(False)
            self._expanded_width = max(
                self._requested_expanded_width, self.expanded_width_hint())
            end = self._expanded_width
        else:
            end = self._collapsed_width
        self._anim.stop()
        self._anim.setStartValue(start)
        self._anim.setEndValue(end)
        self._anim.start()

        if not self._expanded:
            # switch to collapsed mode when animation finished
            def restore():
                self._apply_collapsed_ui(True)
                self._anim.finished.disconnect(restore)

            self._anim.finished.connect(restore)

    def apply_dark_mode(self):
        for idx, btn in enumerate(self._menu_buttons):
            btn.setIcon(self._dark_icons[idx])

    def apply_light_mode(self):
        for idx, btn in enumerate(self._menu_buttons):
            btn.setIcon(self._light_icons[idx])
