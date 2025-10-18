# -*- coding: utf-8 -*-
from functools import partial

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
    QWidget, QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QGridLayout, QScrollArea, QFrame, QButtonGroup, QSizePolicy
)

import config
from models.widgets import RecentAreaBar


class AreaPickerPanel(QDialog):
    CHILD_COLS = 4  # 每行 4 个
    CHILD_BTN_W = 130
    PARENT_BTN_W = 90
    CHILD_BTN_H = 36
    CHILD_H_GAP = 15
    CHILD_V_GAP = 20
    PARENT_H_GAP = 62
    FOOTER_BTN_H = 30
    selectionConfirmed = Signal(str, str)  # parent, child
    historyUpdated = Signal(object)

    def __init__(self, /, parent: QWidget | None = None, *,
                 recent_pairs: list[tuple[str, str]] | None = None):
        super().__init__(parent)
        self.setWindowTitle("直播分区")
        self.setModal(True)
        self.setFixedSize(610, 520)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)

        # 状态
        self._selected_parent: str | None = None
        self._selected_child: str | None = None
        self._all_child_buttons: list[QPushButton] = []

        # ===== 布局骨架 =====
        root = QVBoxLayout(self)
        root.setAlignment(Qt.AlignmentFlag.AlignTop)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(12)

        # 顶部：当前分区
        top_line = QHBoxLayout()
        self.current_label = QLabel("当前分区：-")
        top_line.addWidget(self.current_label, 1, Qt.AlignmentFlag.AlignLeft)
        root.addLayout(top_line)

        # 最近开播
        recent_wrap = QVBoxLayout()
        recent_row = QHBoxLayout()
        recent_row.addWidget(QLabel("最近开播："))

        self.recent_bar = RecentAreaBar(self)
        recent_row.addWidget(self.recent_bar, 1)
        recent_wrap.addLayout(recent_row)
        root.addLayout(recent_wrap)
        self.recent_bar.pairSelected.connect(self._quick_pick)
        self.recent_pairs = recent_pairs
        if recent_pairs is not None:
            self.recent_bar.set_recent_pairs(recent_pairs)
        self.historyUpdated.connect(self.set_recent_pairs)

        # 搜索框
        search_row = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("输入以过滤子分区…")
        self.search_edit.textChanged.connect(self._apply_child_filter)
        search_row.addWidget(self.search_edit)
        root.addLayout(search_row)

        # 父分区条（横向按钮组，可滚动）
        parent_bar = QScrollArea()
        parent_bar.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        parent_bar.setWidgetResizable(True)
        parent_bar.setFrameShape(QFrame.Shape.NoFrame)
        parent_bar.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        parent_bar.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        parent_inner = QWidget()
        self.parent_layout = QGridLayout(parent_inner)
        self.parent_layout.setContentsMargins(0, 0, 0, 0)
        self.parent_layout.setHorizontalSpacing(self.CHILD_H_GAP)
        parent_bar.setWidget(parent_inner)
        parent_bar.setFixedHeight(self.PARENT_H_GAP)
        root.addWidget(parent_bar)

        self.parent_group = QButtonGroup(self)
        self.parent_group.setExclusive(True)

        # 子分区网格（可滚动）
        child_area = QScrollArea()
        child_area.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        child_area.setWidgetResizable(True)
        child_area.setFrameShape(QFrame.Shape.NoFrame)
        child_area.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        child_area.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.child_inner = QWidget()
        self.child_layout = QGridLayout(self.child_inner)
        self.child_layout.setHorizontalSpacing(self.CHILD_H_GAP)
        self.child_layout.setVerticalSpacing(self.CHILD_V_GAP)
        self.child_layout.setContentsMargins(0, 0, 0, 0)
        self.child_layout.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)

        child_area.setWidget(self.child_inner)
        root.addWidget(child_area, 1)

        self.child_group = QButtonGroup(self)
        self.child_group.setExclusive(True)

        # 底部按钮
        bottom = QHBoxLayout()
        # bottom.addStretch(1)
        self.ok_btn = QPushButton("确认")
        self.ok_btn.setEnabled(False)
        self.ok_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.ok_btn.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.ok_btn.setMinimumHeight(self.FOOTER_BTN_H)
        self.ok_btn.setSizePolicy(QSizePolicy.Policy.Preferred,
                                  QSizePolicy.Policy.Fixed)
        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.setMinimumHeight(self.FOOTER_BTN_H)
        self.cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel_btn.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.cancel_btn.setSizePolicy(QSizePolicy.Policy.Preferred,
                                      QSizePolicy.Policy.Fixed)
        bottom.addWidget(self.ok_btn)
        bottom.addWidget(self.cancel_btn)
        root.addLayout(bottom)

        self.ok_btn.clicked.connect(self._confirm)
        self.cancel_btn.clicked.connect(self.reject)

        self._build_parent_buttons(config.parent_area)

    def set_initial_selection(self, parent_text: str | None,
                              child_text: str | None):
        if parent_text and parent_text in config.parent_area:
            self._select_parent(parent_text)
            if child_text and parent_text in config.area_options and child_text in \
                    config.area_options[parent_text]:
                self._select_child(child_text)

    def _build_parent_buttons(self, parents: list[str]):
        # 先清空
        while self.parent_layout.count():
            item = self.parent_layout.takeAt(0)
            w = item.widget()
            if w:
                self.parent_group.removeButton(w)
                w.deleteLater()

        # 生成
        cols = len(parents)
        for i, name in enumerate(parents):
            btn = QPushButton(name)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
            btn.setCheckable(True)

            # 固定大小，避免随文本伸缩
            btn.setFixedSize(self.PARENT_BTN_W, self.CHILD_BTN_H)
            btn.setSizePolicy(QSizePolicy.Policy.Fixed,
                              QSizePolicy.Policy.Fixed)

            fm = btn.fontMetrics()
            elided = fm.elidedText(name, Qt.TextElideMode.ElideRight,
                                   self.PARENT_BTN_W - 16)  # 预留一点左右 padding
            btn.setText(elided)
            btn.setToolTip(name)

            self.parent_group.addButton(btn)
            r, c = divmod(i, cols)
            self.parent_layout.addWidget(btn, r, c)
            btn.clicked.connect(partial(self._on_parent_clicked, name))

        if parents:
            self._select_parent(parents[0])

    def _populate_children(self, parent_text: str):
        # 清空旧子分区
        self._all_child_buttons.clear()
        while self.child_layout.count():
            item = self.child_layout.takeAt(0)
            w = item.widget()
            if w:
                self.child_group.removeButton(w)
                w.deleteLater()

        children = config.area_options.get(parent_text, [])
        for i, name in enumerate(children):
            btn = QPushButton(name)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
            btn.setCheckable(True)

            btn.setFixedSize(self.CHILD_BTN_W, self.CHILD_BTN_H)
            btn.setSizePolicy(QSizePolicy.Policy.Fixed,
                              QSizePolicy.Policy.Fixed)

            fm = btn.fontMetrics()
            elided = fm.elidedText(name, Qt.TextElideMode.ElideRight,
                                   self.CHILD_BTN_W - 16)
            btn.setText(elided)
            btn.setToolTip(name)

            self.child_group.addButton(btn)
            r, c = divmod(i, self.CHILD_COLS)
            self.child_layout.addWidget(btn, r, c)
            btn.clicked.connect(partial(self._on_child_clicked, name))
            self._all_child_buttons.append(btn)

        # 应用一次过滤（若搜索框里已有文字）
        self._apply_child_filter(self.search_edit.text())

        # 子分区变化后，需重置确认按钮与当前展示
        self._selected_child = None
        self._sync_current_label()
        self._update_ok_enabled()

    @Slot(str)
    def _on_parent_clicked(self, parent_text: str):
        self._selected_parent = parent_text
        self._populate_children(parent_text)
        self._sync_current_label()

    @Slot(str)
    def _on_child_clicked(self, child_text: str):
        self._selected_child = child_text
        self.recent_bar.select_recent(self._selected_parent,
                                      self._selected_child)
        self._sync_current_label()
        self._update_ok_enabled()

    @Slot(object)
    def set_recent_pairs(self, pairs):
        self.recent_pairs = list(pairs or [])
        self.recent_bar.set_recent_pairs(pairs)

    @Slot(str)
    def _apply_child_filter(self, keyword: str):
        kw = (keyword or "").strip()

        def _match(_btn):
            return True if not kw else (kw in _btn.text())

        matched = []
        for btn in self._all_child_buttons:
            ok = _match(btn)
            if btn.hasFocus() and not ok:
                self.search_edit.setFocus(Qt.FocusReason.TabFocusReason)
            btn.setVisible(ok)  # 视觉隐藏/显示
            if ok:
                matched.append(btn)
            else:
                # 如果被隐藏的是当前选中按钮，清理选择，避免“已选但不可见”
                if btn.isChecked():
                    btn.setChecked(False)
                    if self._selected_child == btn.text():
                        self._selected_child = None

        self._reflow_children(matched, kw)

        self._sync_current_label()
        self._update_ok_enabled()

    def _reflow_children(self, buttons: list[QPushButton], kw: str):
        self._clear_layout_keep_widgets()

        def _key(b):
            t = b.text()
            if kw:
                rank = 0 if t.startswith(kw) else (1 if kw in t else 2)
            else:
                rank = 0
            return rank, t.casefold()

        buttons.sort(key=_key)

        cols = self.CHILD_COLS
        for i, btn in enumerate(buttons):
            r, c = divmod(i, cols)
            self.child_layout.addWidget(btn, r, c)

        # 触发布局更新
        self.child_inner.adjustSize()
        self.child_inner.updateGeometry()

    def _clear_layout_keep_widgets(self):
        while self.child_layout.count():
            item = self.child_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                self.child_layout.removeWidget(w)

    def _quick_pick(self, parent_text: str, child_text: str):
        self._select_parent(parent_text)
        self._select_child(child_text)

    def _select_parent(self, parent_text: str):
        for btn in self.parent_group.buttons():
            if btn.text() == parent_text:
                btn.setChecked(True)
                break
        self._on_parent_clicked(parent_text)

    def _select_child(self, child_text: str):
        for btn in self.child_group.buttons():
            if btn.text() == child_text and btn.isVisible():
                btn.setChecked(True)
                self._on_child_clicked(child_text)
                break

    def _sync_current_label(self):
        p = self._selected_parent or ""
        c = self._selected_child or ""
        self.current_label.setText(f"当前分区：{p} - {c}")

    def _update_ok_enabled(self):
        self.ok_btn.setEnabled(
            bool(self._selected_parent and self._selected_child))

    def _confirm(self):
        if not (self._selected_parent and self._selected_child):
            return
        self.selectionConfirmed.emit(self._selected_parent,
                                     self._selected_child)
        self.accept()
