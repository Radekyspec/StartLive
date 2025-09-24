from os.path import join

from PySide6.QtCore import Qt, QEasingCurve, QVariantAnimation, QSize
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QVBoxLayout, QFrame, QToolButton,
    QSizePolicy
)


class SideBar(QFrame):
    def __init__(self, parent=None, *, icon_path: str, expanded_width: int,
                 collapsed_width: int):
        super().__init__(parent)
        self._expanded_width = expanded_width
        self._collapsed_width = collapsed_width
        self._icon_path = icon_path
        self._expanded = False
        self.setObjectName("SideBar")
        self.setFixedWidth(self._collapsed_width)
        self._light_icons = [
            QIcon(join(icon_path, "light-menu.svg")),
            QIcon(join(icon_path, "light-theme.svg")),
            QIcon(join(icon_path, "light-home.svg")),
            QIcon(join(icon_path, "light-log.svg")),
            QIcon(join(icon_path, "light-settings.svg")),
        ]
        self._dark_icons = [
            QIcon(join(icon_path, "dark-menu.svg")),
            QIcon(join(icon_path, "dark-theme.svg")),
            QIcon(join(icon_path, "dark-home.svg")),
            QIcon(join(icon_path, "dark-log.svg")),
            QIcon(join(icon_path, "dark-settings.svg")),
        ]

        def mk_btn(text: str, icon_index, *, checkable: bool = True):
            b = QToolButton()
            b.setProperty("_fulltext", text)
            b.setText("" if not self._expanded else text)
            b.setIcon(self._light_icons[icon_index])
            b.setIconSize(QSize(20, 20))
            # icon only when collapsed, icon plus text when expanded
            b.setToolButtonStyle(
                Qt.ToolButtonStyle.ToolButtonIconOnly if not self._expanded
                else Qt.ToolButtonStyle.ToolButtonTextBesideIcon
            )
            b.setCheckable(checkable)
            b.setMinimumHeight(40)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setObjectName("MenuButton")
            b.setSizePolicy(QSizePolicy.Policy.Expanding,
                            QSizePolicy.Policy.Preferred)
            return b

        self.toggle_btn = mk_btn(" 菜单", 0, checkable=False)
        self.toggle_btn.clicked.connect(self._toggle)

        self.btn_theme = mk_btn("", 1, checkable=False)
        self.btn_home = mk_btn(" 主界面", 2)
        self.btn_log = mk_btn(" 日志", 3)
        self.btn_settings = mk_btn(" 设置", 4)

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
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._menu_buttons = [
            self.toggle_btn, self.btn_theme, self.btn_home, self.btn_log,
            self.btn_settings
        ]

    def _on_anim_value(self, val):
        self.setFixedWidth(int(val))
        self.updateGeometry()
        if self.parentWidget(): self.parentWidget().updateGeometry()

    def _apply_collapsed_ui(self, collapsed: bool):
        for b in self._menu_buttons:
            full = b.property("_fulltext")
            b.setText("" if collapsed else full)
            b.setToolButtonStyle(
                Qt.ToolButtonStyle.ToolButtonIconOnly if collapsed else Qt.ToolButtonStyle.ToolButtonTextBesideIcon)

    def _toggle(self):
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
