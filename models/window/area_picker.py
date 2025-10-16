# -*- coding: utf-8 -*-
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QGridLayout, QScrollArea, QFrame, QButtonGroup, QSizePolicy
)

import config


class AreaPickerPanel(QDialog):
    selectionConfirmed = Signal(str, str)  # parent, child

    def __init__(self, parent: QWidget | None = None,
                 recent_pairs: list[tuple[str, str]] | None = None):
        super().__init__(parent)
        self.setWindowTitle("直播分区")
        self.setModal(True)
        self.setGeometry(300, 200, 610, 470)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)

        # 状态
        self._selected_parent: str | None = None
        self._selected_child: str | None = None
        self._all_child_buttons: list[QPushButton] = []

        # ===== 布局骨架 =====
        root = QVBoxLayout(self)
        root.setAlignment(Qt.AlignmentFlag.AlignTop)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        # 顶部：当前分区
        top_line = QHBoxLayout()
        self.current_label = QLabel("当前分区：-")
        top_line.addWidget(self.current_label, 1, Qt.AlignmentFlag.AlignLeft)
        root.addLayout(top_line)

        # 最近开播
        recent_wrap = QVBoxLayout()
        recent_row = QHBoxLayout()
        recent_row.addWidget(QLabel("最近开播："))
        self.recent_container = QHBoxLayout()
        self.recent_container.setSpacing(6)
        recent_row.addLayout(self.recent_container, 1)
        recent_wrap.addLayout(recent_row)
        root.addLayout(recent_wrap)

        if recent_pairs:
            for p, c in recent_pairs:
                btn = QPushButton(f"{p} - {c}")
                btn.setCheckable(False)
                btn.clicked.connect(
                    lambda _, pp=p, cc=c: self._quick_pick(pp, cc))
                self.recent_container.addWidget(btn)
        else:
            # 没有最近记录也保留结构
            hint = QLabel("（无记录）")
            hint.setEnabled(False)
            self.recent_container.addWidget(hint)

        # 搜索框
        search_row = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("输入以过滤子分区…")
        self.search_edit.textChanged.connect(self._apply_child_filter)
        search_row.addWidget(self.search_edit)
        root.addLayout(search_row)

        # 父分区条（横向按钮组，可滚动）
        parent_bar = QScrollArea()
        parent_bar.setWidgetResizable(True)
        parent_bar.setFrameShape(QFrame.Shape.NoFrame)
        parent_bar.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        parent_bar.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        parent_inner = QWidget()
        self.parent_layout = QGridLayout(parent_inner)
        self.parent_layout.setContentsMargins(0, 0, 0, 0)
        self.parent_layout.setHorizontalSpacing(6)
        self.parent_layout.setVerticalSpacing(6)
        parent_bar.setWidget(parent_inner)
        root.addWidget(parent_bar)

        self.parent_group = QButtonGroup(self)
        self.parent_group.setExclusive(True)

        # 子分区网格（可滚动）
        child_area = QScrollArea()
        child_area.setWidgetResizable(True)
        child_area.setFrameShape(QFrame.Shape.NoFrame)
        self.child_inner = QWidget()
        self.child_layout = QGridLayout(self.child_inner)
        self.child_layout.setContentsMargins(0, 0, 0, 0)
        self.child_layout.setHorizontalSpacing(6)
        self.child_layout.setVerticalSpacing(6)
        child_area.setWidget(self.child_inner)
        root.addWidget(child_area, 1)

        self.child_group = QButtonGroup(self)
        self.child_group.setExclusive(True)

        # 底部按钮
        bottom = QHBoxLayout()
        bottom.addStretch(1)
        self.ok_btn = QPushButton("确认")
        self.ok_btn.setEnabled(False)
        self.cancel_btn = QPushButton("取消")
        bottom.addWidget(self.ok_btn)
        bottom.addWidget(self.cancel_btn)
        root.addLayout(bottom)

        self.ok_btn.clicked.connect(self._confirm)
        self.cancel_btn.clicked.connect(self.reject)

        self._build_parent_buttons(config.parent_area)

    def set_initial_selection(self, parent_text: str | None,
                              child_text: str | None):
        """可选：设置默认选中的父/子分区（若存在则选中并同步 UI）"""
        if parent_text and parent_text in config.parent_area:
            self._select_parent(parent_text)
            if child_text and parent_text in config.area_options and child_text in \
                    config.area_options[parent_text]:
                self._select_child(child_text)

    # ---------- 内部构建 ----------
    def _build_parent_buttons(self, parents: list[str]):
        """构建父分区按钮条：网格布局以形成“标签条”的视觉节奏。"""
        # 先清空
        while self.parent_layout.count():
            item = self.parent_layout.takeAt(0)
            w = item.widget()
            if w:
                self.parent_group.removeButton(w)
                w.deleteLater()

        # 生成
        cols = 6  # 每行显示的父分区按钮数，可按需要调整
        for i, name in enumerate(parents):
            btn = QPushButton(name)
            btn.setCheckable(True)
            btn.setSizePolicy(QSizePolicy.Policy.Preferred,
                              QSizePolicy.Policy.Fixed)
            self.parent_group.addButton(btn)
            r, c = divmod(i, cols)
            self.parent_layout.addWidget(btn, r, c)
            btn.clicked.connect(
                lambda checked, t=name: self._on_parent_clicked(t))

        # 默认选中第一个（若存在）
        if parents:
            self._select_parent(parents[0])

    def _populate_children(self, parent_text: str):
        """根据父分区填充子分区网格。逻辑参考原先的 update_child_combo。"""
        # 清空旧子分区
        self._all_child_buttons.clear()
        while self.child_layout.count():
            item = self.child_layout.takeAt(0)
            w = item.widget()
            if w:
                self.child_group.removeButton(w)
                w.deleteLater()

        children = config.area_options.get(parent_text, [])
        cols = 4  # 每行显示的子分区按钮数
        for i, name in enumerate(children):
            btn = QPushButton(name)
            btn.setCheckable(True)
            self.child_group.addButton(btn)
            r, c = divmod(i, cols)
            self.child_layout.addWidget(btn, r, c)
            btn.clicked.connect(
                lambda checked, t=name: self._on_child_clicked(t))
            self._all_child_buttons.append(btn)

        # 应用一次过滤（若搜索框里已有文字）
        self._apply_child_filter(self.search_edit.text())

        # 子分区变化后，需重置确认按钮与当前展示
        self._selected_child = None
        self._sync_current_label()
        self._update_ok_enabled()

    # ---------- 事件与交互 ----------
    def _on_parent_clicked(self, parent_text: str):
        self._selected_parent = parent_text
        self._populate_children(parent_text)
        # 与原逻辑一致：切换父分区即刷新子分区列表
        self._sync_current_label()

    def _on_child_clicked(self, child_text: str):
        self._selected_child = child_text
        self._sync_current_label()
        self._update_ok_enabled()

    def _apply_child_filter(self, keyword: str):
        """包含式过滤 + 重排，不依赖 isVisible()"""
        kw = (keyword or "").strip()

        def _match(btn):
            # 关键：用文本匹配决定“逻辑可见性”
            return True if not kw else (kw in btn.text())

        matched = []
        for btn in self._all_child_buttons:
            ok = _match(btn)
            btn.setVisible(ok)  # 视觉隐藏/显示
            if ok:
                matched.append(btn)
            else:
                # 如果被隐藏的是当前选中按钮，清理选择，避免“已选但不可见”
                if btn.isChecked():
                    btn.setChecked(False)
                    if self._selected_child == btn.text():
                        self._selected_child = None

        # 按“匹配度 + 字典序”重排，初次进入 kw=='' 时会显示全部
        self._reflow_children(matched, kw)

        self._sync_current_label()
        self._update_ok_enabled()

    def _reflow_children(self, buttons: list[QPushButton], kw: str):
        """把待显示的按钮按新顺序紧凑铺回网格"""
        self._clear_layout_keep_widgets(self.child_layout)

        # 排序策略：前缀匹配优先（kw 开头）→ 普通包含 → 文本字典序
        def _key(b):
            t = b.text()
            if kw:
                rank = 0 if t.startswith(kw) else (1 if kw in t else 2)
            else:
                rank = 0
            return rank, t.casefold()

        buttons.sort(key=_key)

        cols = 4
        for i, btn in enumerate(buttons):
            r, c = divmod(i, cols)
            self.child_layout.addWidget(btn, r, c)

        # 触发布局更新
        self.child_inner.adjustSize()
        self.child_inner.updateGeometry()

    def _clear_layout_keep_widgets(self, layout):
        """取出布局项但不销毁 widget，本质是‘清格子不清按钮’"""
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w is not None:
                layout.removeWidget(w)

    def _quick_pick(self, parent_text: str, child_text: str):
        """从‘最近开播’快速选中一组。"""
        self._select_parent(parent_text)
        self._select_child(child_text)

    # ---------- 选择/UI 同步 ----------
    def _select_parent(self, parent_text: str):
        # 触发父分区按钮的选中
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
        p = self._selected_parent or "-"
        c = self._selected_child or "-"
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

# ============ 用法示例 ============
# 将该对话框与原 StreamConfigPanel 对接的典型方式（示意）：
#
# def open_area_picker(self):
#     dlg = AreaPickerPanel(self, recent_pairs=[("网游", "命运方舟"), ("手游", "明日方舟")])
#     # 可选：设置默认选中
#     # dlg.set_initial_selection(config.room_info.get("parent_area"), config.room_info.get("area"))
#     def _apply(parent_text, child_text):
#         # 将选择结果写回你原先的控件/状态，然后沿用现有保存逻辑
#         self.parent_combo.setEditText(parent_text)
#         self.update_child_combo(parent_text)  # 维持与旧逻辑一致
#         self.child_combo.setEditText(child_text)
#         self._activate_area_save()
#     dlg.selectionConfirmed.connect(_apply)
#     dlg.exec()
