from pathlib import Path

from PySide6.QtCore import QEasingCurve, QSize, Qt, QVariantAnimation, Slot
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QFrame, QSizePolicy, QToolButton, QVBoxLayout


def _safe_int(value: float) -> int:
    try:
        return int(value)
    except (OverflowError, TypeError, ValueError) as exc:
        raise ValueError("Expected a finite animation value") from exc


class SideBar(QFrame):
    def __init__(
        self, parent=None, *, icon_path: Path, expanded_width: int, collapsed_width: int
    ):
        super().__init__(parent)
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

        v = QVBoxLayout(self)
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
            self.toggle_btn,
            self.btn_theme,
            self.btn_home,
            self.btn_log,
            self.btn_settings,
        ]

    def _make_button(
        self,
        text: str,
        icon_index: int,
        *,
        checkable: bool = True,
        tooltip: str | None = None,
    ) -> QToolButton:
        button = QToolButton()
        label = tooltip or text.strip()
        button.setProperty("_fulltext", text)
        button.setToolTip(label)
        button.setAccessibleName(label)
        button.setText("" if not self._expanded else text)
        button.setIcon(self._light_icons[icon_index])
        button.setIconSize(QSize(20, 20))
        # icon only when collapsed, icon plus text when expanded
        button.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonIconOnly
            if not self._expanded
            else Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        )
        button.setCheckable(checkable)
        button.setMinimumHeight(40)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setObjectName("MenuButton")
        button.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        return button

    @Slot()
    def _on_anim_finished(self):
        self._anim_changing = False

    @Slot()
    def _on_anim_value(self, val):
        self.setFixedWidth(_safe_int(val))
        self.updateGeometry()
        parent = self.parentWidget()
        if parent is not None:
            parent.updateGeometry()

    def _apply_collapsed_ui(self, collapsed: bool):
        for b in self._menu_buttons:
            full = b.property("_fulltext")
            b.setText("" if collapsed else full)
            b.setToolButtonStyle(
                Qt.ToolButtonStyle.ToolButtonIconOnly
                if collapsed
                else Qt.ToolButtonStyle.ToolButtonTextBesideIcon
            )

    @Slot()
    def _toggle(self):
        if self._anim_changing:
            return
        self._anim_changing = True
        self._expanded = not self._expanded
        start = self.width()
        end = self._expanded_width if self._expanded else self._collapsed_width
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
        else:
            # switch to full mode immediately
            self._apply_collapsed_ui(False)

    def apply_dark_mode(self):
        for idx, btn in enumerate(self._menu_buttons):
            btn.setIcon(self._dark_icons[idx])

    def apply_light_mode(self):
        for idx, btn in enumerate(self._menu_buttons):
            btn.setIcon(self._light_icons[idx])
