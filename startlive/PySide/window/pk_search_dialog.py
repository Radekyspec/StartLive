from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QPushButton, QVBoxLayout,
)

from startlive.PySide.interface_adapters.pk.pk_presenter import PkPresenter
from startlive.core.pk.identity import require_current_identity
from startlive.core.workers.pk.search_candidates import PkSearchCandidatesWorker


class PkSearchDialog(QDialog):
    candidateSelected = Signal(object)

    def __init__(self, manager, identity, search, parent=None, *,
                 video_link=False):
        super().__init__(parent)
        self.manager, self.identity = manager, identity
        self._closed = False
        self._busy = False
        self._page = 0
        self._has_next = False
        self._search = ""
        self.video_link = video_link
        self.setWindowTitle("选择视频 PK 对手")
        self.setWindowModality(Qt.WindowModality.WindowModal)
        self.resize(440, 360)
        layout = QVBoxLayout(self)
        row = QHBoxLayout()
        self.query = QLineEdit(search)
        self.query.setPlaceholderText("主播名称 / 房间号")
        self.search_button = QPushButton("查找")
        self.search_button.clicked.connect(self.search)
        self.query.returnPressed.connect(self.search)
        row.addWidget(self.query)
        row.addWidget(self.search_button)
        layout.addLayout(row)
        self.candidates = QListWidget()
        self.candidates.currentRowChanged.connect(
            lambda _: self._update_controls())
        layout.addWidget(self.candidates)
        self.status = QLabel("查找并选择对手后继续。")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        row = QHBoxLayout()
        self.more_button = QPushButton("加载更多")
        self.more_button.clicked.connect(
            lambda: self._request_page(self._page + 1))
        self.select_button = QPushButton("选择对手")
        self.select_button.clicked.connect(self._choose)
        self.close_button = QPushButton("取消")
        self.close_button.clicked.connect(self.reject)
        for button in (self.more_button, self.select_button, self.close_button):
            row.addWidget(button)
        layout.addLayout(row)
        self._update_controls()
        if video_link:
            self.setWindowTitle("选择视频连线对手")
            self.query.hide()
            self.more_button.hide()
            self.search_button.setText("刷新列表")

    def search(self):
        if self._busy or self._closed:
            return
        self._search = self.query.text().strip()
        if not self.video_link and (
                not self._search.isascii() or not self._search.isdecimal() or not 0 < int(
                self._search) < 1 << 64):
            self.status.setText("请输入有效的主播 UID 或房间号")
            return
        self._page, self._has_next = 0, False
        self.candidates.clear()
        self._request_page(1)

    def _request_page(self, page):
        if self._busy or self._closed or (page > 1 and not self._has_next):
            return
        self._busy = True
        self._update_controls()
        self.status.setText("正在查找对手…")
        presenter = PkPresenter(finished=self._loaded, failed=self._failed)
        worker_type = PkSearchCandidatesWorker
        if self.video_link:
            from startlive.core.workers.pk.video_link import PkLinkPanelWorker
            worker_type = PkLinkPanelWorker
        worker = worker_type(presenter, self.identity,
                                          self._search, page=page)
        try:
            self.manager.submit(worker)
        except Exception as error:
            self._failed(error)

    def _loaded(self, page):
        if self._closed:
            return
        self._busy = False
        self._page, self._has_next = page.page, page.has_next
        for candidate in page.users:
            if self.video_link and (
                    candidate.uid == self.identity.uid or not candidate.label_type
                    or candidate.biz_session_id or candidate.raw.get(
                "other_users_num", 0)):
                continue
            title = f"{candidate.uname or '未命名用户'}  ·  UID {candidate.uid}"
            if candidate.label:
                title += f"\n{candidate.label}"
            item = QListWidgetItem(title)
            item.setData(Qt.ItemDataRole.UserRole, candidate)
            self.candidates.addItem(item)
        self.status.setText(
            "请选择对手；是否可以邀请还需服务端检查。" if self.candidates.count() else
            "未找到匹配的主播，邀请尚未发送。可尝试主播 UID 或房间号。")
        self._update_controls()

    def _failed(self, error):
        if self._closed:
            return
        self._busy = False
        self.status.setText(str(error))
        self._update_controls()

    def _update_controls(self):
        self.query.setEnabled(not self._busy)
        self.search_button.setEnabled(not self._busy)
        self.more_button.setEnabled(not self._busy and self._has_next)
        self.select_button.setEnabled(
            not self._busy and self.candidates.currentItem() is not None)

    def _choose(self):
        if self._busy or self._closed or self.candidates.currentItem() is None:
            return
        try:
            require_current_identity(self.identity)
        except Exception as error:
            self._failed(error)
            return
        candidate = self.candidates.currentItem().data(Qt.ItemDataRole.UserRole)
        self.candidateSelected.emit(candidate)
        self.accept()

    def done(self, result):
        # Search is read-only; ignore a pending HTTP result after dismissal.
        self._closed = True
        super().done(result)
