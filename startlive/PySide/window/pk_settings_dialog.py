from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from startlive.core.pk.states.preferences import PkPreferenceValues


class PkSettingsDialog(QDialog):
    """Display confirmed settings and emit user intent without changing them."""

    changeRequested = Signal(str, object)
    refreshRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("PK / 连线设置")
        self._values = None
        self._duration_options = ()
        self._busy = False
        self.checkboxes = {}
        layout = QVBoxLayout(self)

        pk_group = QGroupBox("PK设置")
        pk_layout = QFormLayout(pk_group)
        self.duration = QComboBox()
        self.duration.activated.connect(self._duration_changed)
        pk_layout.addRow("我发起邀请的PK时长", self.duration)
        for field, label in (
                ("accept_pk", "接受PK邀请"),
                ("accept_unfollowed_pk", "接受未关注主播的PK邀请"),
                ("classic_pk", "经典PK"),
                ("classic_opponent_voice", "经典PK开启对方主播语音"),
        ):
            pk_layout.addRow(self._checkbox(field, label))
        layout.addWidget(pk_group)

        connection_group = QGroupBox("连线设置")
        connection_layout = QVBoxLayout(connection_group)
        for field, label in (
                ("accept_connection", "接受连线邀请"),
                ("mutual_only", "只接受互关主播连线邀请"),
                ("allow_apply_join", "是否允许申请加入"),
                ("allow_auto_join", "是否允许自动加入"),
                ("allow_other_invite", "是否允许其他用户邀请加入"),
        ):
            connection_layout.addWidget(self._checkbox(field, label))
        layout.addWidget(connection_group)

        self.status = QLabel()
        self.error = QLabel()
        self.error.setTextFormat(Qt.TextFormat.PlainText)
        self.error.setWordWrap(True)
        layout.addWidget(self.status)
        layout.addWidget(self.error)
        buttons = QHBoxLayout()
        self.refresh_button = QPushButton("刷新")
        self.refresh_button.clicked.connect(self.refreshRequested)
        self.close_button = QPushButton("关闭")
        self.close_button.clicked.connect(self.close)
        buttons.addWidget(self.refresh_button)
        buttons.addStretch()
        buttons.addWidget(self.close_button)
        layout.addLayout(buttons)
        self._render()

    def _checkbox(self, field, label):
        control = QCheckBox(label)
        control.clicked.connect(lambda checked: self._change(field, checked))
        self.checkboxes[field] = control
        return control

    def set_values(self, values: PkPreferenceValues,
                   duration_options: tuple[tuple[int, str], ...]):
        """Accept GET values or submitted values confirmed by a successful save."""
        self._values = values
        self._duration_options = tuple(duration_options)
        self.error.clear()
        self._render()

    def set_busy(self, busy: bool):
        self._busy = busy
        self._render()

    def clear_values(self):
        self._values = None
        self._duration_options = ()
        self.error.clear()
        self._render()

    def set_error(self, text: str):
        self.error.setText(text)
        self._render()

    def _render(self):
        loaded = self._values is not None
        editable = loaded and not self._busy
        for field, control in self.checkboxes.items():
            with QSignalBlocker(control):
                control.setTristate(not loaded)
                if loaded:
                    control.setChecked(getattr(self._values, field))
                else:
                    control.setCheckState(Qt.CheckState.PartiallyChecked)
            control.setEnabled(editable and (
                    field != "classic_opponent_voice" or self._values.classic_pk))
        with QSignalBlocker(self.duration):
            self.duration.clear()
            for value, label in self._duration_options:
                self.duration.addItem(label, value)
            self.duration.setPlaceholderText(
                "未读取" if not loaded else
                "暂无可选时长" if not self._duration_options else "当前时长不在可选项中")
            self.duration.setCurrentIndex(
                self.duration.findData(self._values.duration) if loaded else -1)
        self.duration.setEnabled(editable and bool(self._duration_options))
        self.refresh_button.setEnabled(not self._busy)
        self.status.setText(
            ("正在更新" if loaded else "正在读取") if self._busy else
            "已读取" if loaded else "未读取")

    def _duration_changed(self, index):
        value = self.duration.itemData(index)
        if value is not None:
            self._change("duration", value)

    def _change(self, field, value):
        # The controller owns coupling and persistence. Keep the confirmed
        # snapshot visible until it confirms fetched or saved values with set_values.
        self._render()
        if (field == "classic_opponent_voice"
                and not self.checkboxes[field].isEnabled()):
            return
        if (self._values is not None and not self._busy
                and value != getattr(self._values, field)):
            self.changeRequested.emit(field, value)
