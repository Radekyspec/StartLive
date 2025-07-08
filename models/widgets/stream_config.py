# -*- coding: utf-8 -*-

# module import
from functools import partial
from ipaddress import ip_address, IPv6Address

# package import
from PySide6.QtCore import (Qt, QTimer)
from PySide6.QtGui import QIntValidator
from PySide6.QtWidgets import (QCheckBox, QGridLayout, QGroupBox,
                               QHBoxLayout,
                               QLabel, QLineEdit, QPushButton,
                               QVBoxLayout, QWidget,
                               QApplication)

# local package import
import config
from models.classes import FocusAwareLineEdit, \
    CompletionComboBox
from models.workers import *


class StreamConfigPanel(QWidget):

    def __init__(self, parent_window):
        super().__init__()
        self.parent_window = parent_window

        self._obs_timer = QTimer()
        self.main_layout = QVBoxLayout()
        self.setLayout(self.main_layout)
        self.main_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        def _addr_save():
            config.obs_settings["ip_addr"] = self.host_input.text()

        def _port_save():
            config.obs_settings["port"] = self.port_input.text()

        def _password_save():
            config.obs_settings["password"] = self.pass_input.text()

        def _auto_live_save():
            config.obs_settings[
                "auto_live"] = self.obs_auto_live_checkbox.isChecked()

        def _auto_connect_save():
            config.obs_settings[
                "auto_connect"] = self.obs_auto_connect_checkbox.isChecked()

        # 顶部区域：OBS 连接信息
        obs_group = QGroupBox("OBS 连接设置")
        obs_layout = QGridLayout()

        obs_layout.addWidget(QLabel("服务器IP:"), 1, 0)
        self.host_input = QLineEdit("localhost")
        self.host_input.editingFinished.connect(_addr_save)
        obs_layout.addWidget(self.host_input, 1, 1)

        obs_layout.addWidget(QLabel("端口:"), 1, 2)
        self.port_input = QLineEdit("4455")
        self.port_input.setValidator(QIntValidator(1, 65535))
        self.port_input.editingFinished.connect(_port_save)
        obs_layout.addWidget(self.port_input, 1, 3)

        obs_layout.addWidget(QLabel("服务器密码:"), 1, 4)
        self.pass_input = QLineEdit()
        self.pass_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.pass_input.editingFinished.connect(_password_save)
        obs_layout.addWidget(self.pass_input, 1, 5)

        self.connect_btn = QPushButton("连接")
        self.connect_btn.clicked.connect(self._connect_obs)
        obs_layout.addWidget(self.connect_btn, 1, 6)
        self._obs_timer.timeout.connect(self._obs_btn_state)

        obs_hint = QLabel(
            "在 OBS 中打开 WebSocket服务器 功能，在下方填写信息以自动导入推流地址到OBS\n未连接 OBS 时自动推流将不会生效")
        obs_hint.setStyleSheet("color: red")
        obs_hint.setWordWrap(True)
        obs_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        obs_layout.addWidget(obs_hint, 0, 0, 1, 7)

        obs_auto_start = QWidget()
        obs_auto_start_layout = QHBoxLayout()
        obs_auto_start_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.obs_auto_live_checkbox = QCheckBox("自动推流")
        self.obs_auto_live_checkbox.setToolTip(
            "勾选此项后，软件内点击开播时会自动点击OBS的推流"
        )
        self.obs_auto_live_checkbox.setChecked(False)
        self.obs_auto_live_checkbox.setEnabled(False)
        self.obs_auto_live_checkbox.checkStateChanged.connect(_auto_live_save)
        obs_auto_start_layout.addWidget(self.obs_auto_live_checkbox)
        self.obs_auto_connect_checkbox = QCheckBox("自动连接OBS")
        self.obs_auto_connect_checkbox.setToolTip(
            "勾选此项后，软件打开时会自动尝试连接OBS"
        )
        self.obs_auto_connect_checkbox.checkStateChanged.connect(
            _auto_connect_save)
        self.obs_auto_connect_checkbox.setChecked(False)
        self.obs_auto_connect_checkbox.setEnabled(True)
        obs_auto_start_layout.addWidget(self.obs_auto_connect_checkbox)

        obs_auto_start.setLayout(obs_auto_start_layout)
        obs_layout.addWidget(obs_auto_start, 2, 0, 1, 7)

        obs_group.setLayout(obs_layout)
        self.main_layout.addWidget(obs_group, stretch=1)

        # 中部区域：推流地址与密钥
        stream_group = QGroupBox("推流信息 (自动生成)")
        stream_layout = QGridLayout()

        stream_layout.addWidget(QLabel("串流地址:"), 0, 0, 1, 1)
        self.addr_input = QLineEdit()
        self.addr_input.setReadOnly(True)
        stream_layout.addWidget(self.addr_input, 0, 1, 1, 6)
        self.copy_addr_btn = QPushButton("复制")
        stream_layout.addWidget(self.copy_addr_btn, 0, 8)

        stream_layout.addWidget(QLabel("串流密钥:"), 1, 0, 1, 1)
        self.key_input = FocusAwareLineEdit()
        self.key_input.setReadOnly(True)
        stream_layout.addWidget(self.key_input, 1, 1, 1, 6)
        self.copy_key_btn = QPushButton("复制")
        stream_layout.addWidget(self.copy_key_btn, 1, 8)

        stream_group.setLayout(stream_layout)
        self.main_layout.addWidget(stream_group, stretch=1)

        # 分区选择
        area_group = QGroupBox("直播信息")
        area_group_layout = QGridLayout()
        area_group_layout.addWidget(QLabel("房间标题:"), 0, 0, 1, 1)
        self.title_input = QLineEdit()
        area_group_layout.addWidget(self.title_input, 0, 1, 1, 6)
        self.save_title_btn = QPushButton("保存")
        self.save_title_btn.clicked.connect(self._save_title)
        area_group_layout.addWidget(self.save_title_btn, 0, 8)

        area_group_layout.addWidget(QLabel("分区选择:"), 1, 0, 1, 1)
        self.parent_combo = CompletionComboBox(config.parent_area)
        # self.parent_combo.addItems(config.parent_area)
        area_group_layout.addWidget(self.parent_combo, 1, 1, 1, 3)

        self.child_combo = CompletionComboBox([])
        self.child_combo.setEnabled(False)
        area_group_layout.addWidget(self.child_combo, 1, 4, 1, 3)
        self.save_area_btn = QPushButton("保存")
        self.save_area_btn.setEnabled(False)
        self.save_area_btn.clicked.connect(self._save_area)
        self.parent_combo.editTextChanged.connect(self._activate_area_save)
        self.child_combo.editTextChanged.connect(self._activate_area_save)
        area_group_layout.addWidget(self.save_area_btn, 1, 8)

        area_group.setLayout(area_group_layout)
        self.main_layout.addWidget(area_group, stretch=1)

        # 底部：控制按钮
        control_layout = QHBoxLayout()
        self.start_btn = QPushButton("开始直播")
        self.stop_btn = QPushButton("停止直播")
        self.stop_btn.setEnabled(False)

        control_layout.addStretch()
        control_layout.addWidget(self.start_btn)
        control_layout.addWidget(self.stop_btn)
        control_layout.addStretch()

        self.main_layout.addLayout(control_layout, stretch=1)

        # 绑定逻辑
        self.parent_combo.currentTextChanged.connect(self.update_child_combo)
        self.copy_addr_btn.clicked.connect(self.copy_address)
        self.copy_key_btn.clicked.connect(self.copy_key)
        self.start_btn.clicked.connect(self._start_live)
        self.stop_btn.clicked.connect(self._stop_live)

    def reset_obs_settings(self):
        CredentialManagerWorker.obs_settings_default()
        self.host_input.setText(config.obs_settings["ip_addr"])
        self.port_input.setText(config.obs_settings["port"])
        self.pass_input.setText(config.obs_settings["password"])
        self.obs_auto_connect_checkbox.setChecked(False)
        self.obs_auto_live_checkbox.setChecked(False)

    def update_child_combo(self, text):
        if text in config.area_options:
            self.child_combo.clear()
            self.child_combo.addItems(config.area_options[text])
            self.child_combo.setEnabled(True)
        else:
            self.child_combo.clear()
            self.child_combo.setEnabled(False)

    def _activate_area_save(self):
        self.save_area_btn.setEnabled(True)

    def copy_address(self):
        QApplication.clipboard().setText(self.addr_input.text())

    def copy_key(self):
        QApplication.clipboard().setText(self.key_input.text())

    def start_live(self):
        self._start_live()

    def stop_live(self):
        self._stop_live()

    def _start_live(self):
        if not self._valid_area() or not self.start_btn.isEnabled():
            return
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        # self.parent_combo.setEnabled(False)
        # self.child_combo.setEnabled(False)
        self.save_area_btn.setEnabled(False)
        if config.obs_settings.get("auto_connect",
                                   False) and config.obs_client is None:
            self.connect_btn.click()
        area_code = config.area_codes[self.child_combo.currentText()]
        config.room_info["parent_area"] = self.parent_combo.currentText()
        config.room_info["area"] = self.child_combo.currentText()
        self.parent_window.add_thread(
            StartLiveWorker(area_code),
            on_exception=partial(StartLiveWorker.on_exception, self)
        )
        self.parent_window.timer.timeout.connect(
            self.parent_window.fill_stream_info)
        self.parent_window.timer.start(100)

    def _stop_live(self):
        if not self.stop_btn.isEnabled():
            return
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        # self.parent_combo.setEnabled(True)
        # self.child_combo.setEnabled(True)
        config.stream_status["stream_key"] = None
        config.stream_status["stream_addr"] = None
        self.addr_input.setText("")
        self.key_input.setText("")
        if config.obs_client is not None:
            if self.obs_auto_live_checkbox.isChecked():
                config.obs_req_queue.put(("StopStream", {}))
        self.parent_window.add_thread(
            StopLiveWorker(),
            on_exception=partial(StopLiveWorker.on_exception, self)
        )

    def _connect_obs(self):
        if config.obs_client is None and not config.obs_op:
            self.connect_btn.setText("连接中")
            obs_host = self.host_input.text()
            try:
                ip_object = ip_address(obs_host)
                if isinstance(ip_object, IPv6Address):
                    obs_host = f"[{obs_host}]"
            except ValueError:
                pass
            connector = ObsConnectorWorker(host=obs_host,
                                           port=self.port_input.text(),
                                           password=self.pass_input.text())
            self.parent_window.add_thread(
                connector,
                on_finished=partial(connector.on_finished, self),
                on_exception=partial(connector.on_exception, self)
            )
            self._obs_timer.start(100)
        elif config.obs_client is not None and not config.obs_op:
            ObsDaemonWorker.disconnect_obs()
            self.obs_auto_live_checkbox.setEnabled(False)
            self._obs_timer.start(100)

    def _obs_btn_state(self):
        if config.obs_connecting:
            self.connect_btn.setText("连接中")
            return
        if not config.obs_op:
            self.connect_btn.setText(
                "断开" if config.obs_client is not None else "连接")
            self._obs_timer.stop()

    def _save_title(self):
        self.save_title_btn.setEnabled(False)
        self.parent_window.add_thread(
            TitleUpdateWorker(self.title_input.text()),
            on_exception=partial(TitleUpdateWorker.on_exception, self)
        )

    def _valid_area(self):
        parent_choose = self.parent_combo.currentText()
        if parent_choose == "请选择":
            return False
        return parent_choose in config.parent_area and self.child_combo.currentText() in \
            config.area_options[self.parent_combo.currentText()]

    def _save_area(self):
        if self._valid_area():
            self.save_area_btn.setEnabled(False)
            self.parent_window.add_thread(
                AreaUpdateWorker(self.child_combo.currentText()),
                on_finished=partial(AreaUpdateWorker.on_finished, self),
                on_exception=partial(AreaUpdateWorker.on_exception, self)
            )
