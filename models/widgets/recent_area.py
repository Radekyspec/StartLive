# -*- coding: utf-8 -*-
from functools import partial

from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import QWidget, QHBoxLayout, QPushButton, QLabel, \
    QSizePolicy, QStackedLayout, QButtonGroup


class RecentAreaBar(QWidget):
    CHILD_BTN_H = 36
    pairSelected = Signal(str, str)

    def __init__(self, /, parent=None):
        super().__init__(parent)
        self._pairs: list[tuple[str, str]] = []
        self._stack = QStackedLayout(self)
        self._recent_group = QButtonGroup(self)
        self._recent_group.setExclusive(True)

        empty_page = QWidget(self)
        e_layout = QHBoxLayout(empty_page)
        e_layout.setContentsMargins(0, 0, 0, 0)
        placeholder = QLabel("（无记录）", empty_page)
        placeholder.setEnabled(False)
        e_layout.addWidget(placeholder)
        e_layout.addStretch(1)
        self._stack.addWidget(empty_page)

        self._list_page = QWidget(self)
        self._list_layout = QHBoxLayout(self._list_page)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(6)
        self._stack.addWidget(self._list_page)

        self._stack.setCurrentIndex(0)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def set_recent_pairs(self, pairs):
        self._pairs = list(pairs or [])
        self._rebuild()

    def _rebuild(self):
        for w in self._recent_group.buttons():
            self._recent_group.removeButton(w)
            w.deleteLater()

        if not self._pairs:
            self._stack.setCurrentIndex(0)
            return

        for p, c in self._pairs:
            name = f"{p} - {c}"
            btn = QPushButton(name, self)
            btn.setMinimumHeight(self.CHILD_BTN_H)
            btn.setSizePolicy(QSizePolicy.Policy.Preferred,
                              QSizePolicy.Policy.Fixed)
            fm = btn.fontMetrics()
            elided = fm.elidedText(name, Qt.TextElideMode.ElideRight,
                                   140)
            btn.setText(elided)
            btn.setToolTip(name)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
            btn.setAutoDefault(False)
            btn.setCheckable(True)
            self._recent_group.addButton(btn)
            btn.clicked.connect(partial(self.pairSelected.emit, p, c))
            self._list_layout.addWidget(btn)

        self._stack.setCurrentIndex(1)

    def select_recent(self, parent: str, child: str):
        self._recent_group.setExclusive(False)
        for btn in self._recent_group.buttons():
            if btn.toolTip() == f"{parent} - {child}":
                btn.setChecked(True)
            else:
                btn.setChecked(False)
        self._recent_group.setExclusive(True)
