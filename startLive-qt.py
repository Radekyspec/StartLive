# -*- coding: utf-8 -*-

# module import
import os.path
import sys
from contextlib import suppress
from ipaddress import ip_address, IPv6Address
from typing import Optional

# package import
from PIL import ImageQt
from PySide6.QtCore import (QEvent, Qt, QTimer, QThreadPool)
from PySide6.QtGui import QAction, QIntValidator, QPixmap, QIcon
from PySide6.QtWidgets import (QCheckBox, QGridLayout, QGroupBox,
                               QHBoxLayout,
                               QLabel, QLineEdit, QMessageBox, QPushButton,
                               QVBoxLayout, QWidget,
                               QApplication, QSystemTrayIcon, QMenu
                               )
from darkdetect import isDark
from keyring import set_password, delete_password
from keyring.errors import PasswordDeleteError
from qdarktheme import setup_theme, enable_hi_dpi
from qrcode.main import QRCode

# local package import
import config
import constant
from config import dumps
from constant import *
from models.classes import ClickableLabel, FocusAwareLineEdit, \
    CompletionComboBox, SingleInstanceWindow
from models.workers import *
from models.workers.base import *


class FaceQRWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("人脸认证")
        self.setWindowFlags(
            Qt.WindowType.Window | Qt.WindowType.WindowCloseButtonHint)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        layout = QVBoxLayout()

        self.face_hint = QLabel("目标分区需要人脸认证")
        self.face_hint.setStyleSheet("color: red; font-size: 16pt;")
        self.face_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.face_qr = QLabel()
        self.face_qr.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.face_hint)
        layout.addWidget(self.face_qr)
        self.setLayout(layout)


class StreamConfigPanel(QWidget):
    def __init__(self, parent_window):
        super().__init__()
        self.parent_window = parent_window

        self._obs_timer = QTimer()
        self.main_layout = QVBoxLayout()
        self.setLayout(self.main_layout)
        self.main_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        def _addr_save():
            config.stream_settings["ip_addr"] = self.host_input.text()

        def _port_save():
            config.stream_settings["port"] = self.port_input.text()

        def _password_save():
            config.stream_settings["password"] = self.pass_input.text()

        def _auto_live_save():
            config.stream_settings[
                "auto_live"] = self.obs_auto_live_checkbox.isChecked()

        def _auto_connect_save():
            config.stream_settings[
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
        CredentialManagerWorker.obs_default_settings()
        self.host_input.setText(config.stream_settings["ip_addr"])
        self.port_input.setText(config.stream_settings["port"])
        self.pass_input.setText(config.stream_settings["password"])
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

    def _start_live(self):
        if not self._valid_area():
            return
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        # self.parent_combo.setEnabled(False)
        # self.child_combo.setEnabled(False)
        self.save_area_btn.setEnabled(False)
        if config.stream_settings.get("auto_connect",
                                      False) and config.obs_client is None:
            self.connect_btn.click()
        area_code = config.area_codes[self.child_combo.currentText()]
        config.room_info["parent_area"] = self.parent_combo.currentText()
        config.room_info["area"] = self.child_combo.currentText()
        set_password(KEYRING_SERVICE_NAME, KEYRING_ROOM_INFO,
                     dumps(config.room_info.internal))
        self.parent_window.add_thread(StartLiveWorker(self, area_code))
        self.parent_window.timer.timeout.connect(
            self.parent_window.fill_stream_info)
        self.parent_window.timer.start(100)

    def _stop_live(self):
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
        self.parent_window.add_thread(StopLiveWorker(self))

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
            self.parent_window.add_thread(
                ObsDaemonWorker(self, host=obs_host,
                                port=self.port_input.text(),
                                password=self.pass_input.text()))
        else:
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
            TitleUpdateWorker(self, self.title_input.text()))

    def _valid_area(self):
        parent_choose = self.parent_combo.currentText()
        if parent_choose == "请选择":
            return False
        return parent_choose in config.parent_area and self.child_combo.currentText() in \
            config.area_options[self.parent_combo.currentText()]

    def _save_area(self):
        if self._valid_area():
            self.save_area_btn.setEnabled(False)
            self.parent_window.add_thread(AreaUpdateWorker(self))


# Main GUI window
class MainWindow(SingleInstanceWindow):
    _managed_workers: list[BaseWorker | LongLiveWorker]
    _ll_workers: list[LongLiveWorker]

    def __init__(self):
        super().__init__()
        self._base_interval = 200
        self._worker_interval = 200
        self._max_interval = 10000
        self._thread_pool = QThreadPool()
        self._managed_workers = []
        self._worker_timer = QTimer()
        self.timer = QTimer()
        # Long live workers
        self._ll_workers = []
        self.setWindowTitle(f"StartLive 开播器 {VERSION}")
        self.setGeometry(300, 200, 520, 430)
        self.tray_icon = QSystemTrayIcon(self)
        # https://nuitka.net/user-documentation/common-issue-solutions.html#onefile-finding-files
        self.tray_icon.setIcon(QIcon(
            os.path.join(os.path.dirname(__file__), "resources",
                         "icon_cr.png")))
        self.tray_icon.setToolTip("你所热爱的 就是你的生活")
        self.tray_icon.setVisible(True)

        tray_menu = QMenu()
        restore_action = QAction("显示窗口", self)
        quit_action = QAction("退出", self)
        tray_menu.addAction(restore_action)
        tray_menu.addAction(quit_action)
        self.tray_icon.setContextMenu(tray_menu)
        restore_action.triggered.connect(self.show_normal)
        quit_action.triggered.connect(QApplication.quit)
        self.tray_icon.activated.connect(self.on_tray_icon_activated)

        menu_bar = self.menuBar()
        setting_menu = QMenu("缓存设置", self)
        menu_bar.addMenu(setting_menu)

        delete_cookies_action = QAction("退出账号登录", self)
        delete_cookies_action.triggered.connect(self._delete_cookies)
        setting_menu.addAction(delete_cookies_action)

        delete_settings_action = QAction("清除OBS连接设置", self)
        delete_settings_action.triggered.connect(self._delete_settings)
        setting_menu.addAction(delete_settings_action)

        clear_area_cache = QAction("清除分区缓存", self)
        clear_area_cache.triggered.connect(self._delete_area_cache)
        setting_menu.addAction(clear_area_cache)

        # Widgets for login phase
        self.add_thread(ConstantUpdateWorker())
        self.login_label = QLabel("正在获取保存的登录凭证...")
        self.status_label = ClickableLabel("等待登录中...")
        self.qr_label = QLabel()
        self.panel = StreamConfigPanel(self)

        # Styling and alignment
        for label in [self.login_label, self.status_label]:
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setStyleSheet("font-size: 16pt;")

        self.status_label.setStyleSheet("color: blue; font-size: 16pt;")
        self.qr_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Layout
        layout = QVBoxLayout()
        layout.addWidget(self.login_label)
        layout.addWidget(self.qr_label)
        layout.addWidget(self.status_label)

        central = QWidget()
        central.setLayout(layout)
        self.setCentralWidget(central)

        # Start fetching QR and begin polling thread
        self.credential_worker = CredentialManagerWorker(self)
        self.login_worker = None
        self.add_thread(self.credential_worker)
        self.timer.timeout.connect(self.load_credentials)
        self.timer.start(50)

        # monitor worker health
        self._worker_timer.timeout.connect(self._monitor_exception)
        self._worker_timer.start(self._worker_interval)
        self.face_window: Optional[FaceQRWidget] = None

    def changeEvent(self, event):
        if event.type() == QEvent.Type.WindowStateChange:
            if self.isMinimized():
                QTimer.singleShot(0, self.hide)  # 延迟隐藏窗口
        super().changeEvent(event)

    def closeEvent(self, event):
        # 关闭窗口时退出应用
        self.tray_icon.hide()
        self.tray_icon.deleteLater()
        event.accept()

    def show_normal(self):
        self.show()
        self.setWindowState(Qt.WindowState.WindowActive)

    def on_tray_icon_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.show_normal()

    def _delete_cookies(self):
        if not config.scan_status["scanned"]:
            return
        with suppress(PasswordDeleteError):
            delete_password(KEYRING_SERVICE_NAME, KEYRING_COOKIES)
        QMessageBox.information(self, "账号退出", "账号退出成功, 重启生效")

    def _delete_settings(self):
        with suppress(PasswordDeleteError):
            delete_password(KEYRING_SERVICE_NAME, KEYRING_SETTINGS)
        self.panel.reset_obs_settings()
        QMessageBox.information(self, "设置清空", "OBS连接设置清除成功")

    def _delete_area_cache(self):
        del config.room_info["parent_area"]
        del config.room_info["area"]
        set_password(KEYRING_SERVICE_NAME, KEYRING_ROOM_INFO,
                     dumps(config.room_info.internal))
        QMessageBox.information(self, "分区缓存清空", "分区缓存清除成功")

    def fetch_qr(self, retry=False):
        # Start fetching QR and begin polling thread
        config.scan_status["timeout"] = False
        if retry and self.login_worker is not None:
            self.status_label.clicked.disconnect(self.fetch_qr)
            self.login_worker.stop()
            # Reset status
            config.scan_status.update({
                "qr_key": None, "qr_url": None,
                "wait_for_confirm": False
            })
            self.timer.timeout.connect(self.check_scan_status)
            self.timer.start(100)
        self.add_thread(QRLoginWorker(self))
        self.login_worker = FetchLoginWorker(self)
        self.add_thread(self.login_worker)
        self.login_label.setText("请使用手机扫码登录：")
        self.status_label.setText("等待扫码中...")
        self.status_label.setStyleSheet("color: blue; font-size: 16pt;")
        # Timer checks the login state and updates UI

    def load_credentials(self):
        if self.credential_worker.finished:
            # stop check
            self.timer.timeout.disconnect(self.load_credentials)
            self.timer.stop()
            self.timer.timeout.connect(self.check_scan_status)
            self.timer.start(100)
            if not config.scan_status["scanned"]:
                # Needs update credential
                self.fetch_qr()

    def add_thread(self, worker: BaseWorker | LongLiveWorker):
        self._managed_workers.append(worker)
        if isinstance(worker, LongLiveWorker):
            self._ll_workers.append(worker)
        self._thread_pool.start(worker)

    def _monitor_exception(self):
        done = []
        for worker in self._managed_workers:
            if worker.finished:
                done.append(worker)
                if worker.exception is not None:
                    QMessageBox.critical(self, f"{worker.name}线程错误",
                                         repr(worker.exception))
        for dead_worker in done:
            self._managed_workers.remove(dead_worker)
            if dead_worker in self._ll_workers:
                self._ll_workers.remove(dead_worker)

        if self._managed_workers:
            if len(self._managed_workers) == 1 and len(
                    self._ll_workers) == 1 and any(
                isinstance(item, ObsDaemonWorker) for item in
                self._managed_workers):
                # Only OBS daemon left, no need to check in high frequency
                if self._worker_interval < self._max_interval:
                    self._worker_interval = int(
                        min(self._worker_interval * 1.025,
                            self._max_interval))
            elif self._worker_interval != self._base_interval:
                self._worker_interval = self._base_interval
            self._worker_timer.setInterval(self._worker_interval)
        else:
            if self._worker_interval < self._max_interval:
                self._worker_interval = int(min(self._worker_interval * 1.025,
                                                self._max_interval))
            self._worker_timer.setInterval(self._worker_interval)
        # print(f"worker interval: {self._worker_interval}")

    def on_exit(self):
        if config.stream_settings:
            set_password(KEYRING_SERVICE_NAME, KEYRING_SETTINGS,
                         dumps(config.stream_settings.internal))
        if config.room_info:
            set_password(KEYRING_SERVICE_NAME, KEYRING_ROOM_INFO,
                         dumps(config.room_info.internal))
        for worker in self._ll_workers:
            worker.stop()

    @staticmethod
    # Helper: Generate QR code image from URL
    def generate_qr_code(data: str):
        qr = QRCode(box_size=4, border=1)
        qr.add_data(data)
        qr.make(fit=True)
        if isDark():
            img = qr.make_image(fill_color="white", back_color="black")
        else:
            img = qr.make_image(fill_color="black", back_color="white")
        return img.convert("RGB")

    @classmethod
    # Helper: Convert a PIL image to QPixmap for display in QLabel
    def qpixmap_from_str(cls, data: str):
        return QPixmap.fromImage(ImageQt.ImageQt(cls.generate_qr_code(data)))

    def update_qr_image(self, qr_url: str):
        self.qr_label.setPixmap(self.qpixmap_from_str(qr_url))  # Show in UI

    def after_login_success(self):
        self.timer.timeout.disconnect(self.check_scan_status)
        self.timer.stop()
        config.session.headers.clear()
        config.session.headers.update(constant.HEADERS_APP)
        self.panel.parent_combo.clear()
        self.panel.parent_combo.addItems(config.parent_area)
        self.setCentralWidget(self.panel)
        if config.stream_settings.get("auto_connect", False):
            self.panel.connect_btn.click()
        self.panel.parent_combo.setCurrentText(
            config.room_info.get("parent_area", "请选择"))
        self.panel.child_combo.setCurrentText(
            config.room_info.get("area", ""))

    def check_scan_status(self):
        if config.scan_status["scanned"]:
            # Login succeeded, ready to switch to main UI
            if self.status_label.text() != "登录成功！":
                self.status_label.setText("登录成功！")
                self.status_label.setStyleSheet("color: green;font-size: 16pt;")
            if not config.scan_status["area_updated"] or \
                    not config.scan_status["room_updated"]:
                return
            self.after_login_success()
        elif config.scan_status["timeout"]:
            self.status_label.setText("二维码已失效，点击这里刷新")
            self.status_label.setStyleSheet("color: red; font-size: 16pt;")
            self.status_label.clicked.connect(lambda: self.fetch_qr(True))
            self.timer.timeout.disconnect(self.check_scan_status)
            self.timer.stop()
        elif config.scan_status["wait_for_confirm"]:
            self.status_label.setText("已扫码，等待确认登录...")

    def fill_stream_info(self):
        if config.stream_status["stream_key"] is not None and \
                config.stream_status[
                    "stream_addr"] is not None:
            if config.obs_connecting:
                return
            self.panel.addr_input.setText(
                str(config.stream_status["stream_addr"]))
            self.panel.key_input.setText(
                str(config.stream_status["stream_key"]))

            if config.obs_client is not None:
                config.obs_req_queue.put(("SetStreamServiceSettings", {
                    "streamServiceType": "rtmp_custom",
                    "streamServiceSettings": {
                        "bwtest": False,
                        "server": str(config.stream_status["stream_addr"]),
                        "key": str(config.stream_status["stream_key"]),
                        "use_auth": False
                    }
                }))
                if self.panel.obs_auto_live_checkbox.isChecked():
                    config.obs_req_queue.put(("StartStream", {}))

            self.timer.timeout.disconnect(self.fill_stream_info)
            self.timer.stop()
        elif config.stream_status["required_face"]:
            config.stream_status["required_face"] = False
            self.panel.start_btn.setEnabled(True)
            self.panel.stop_btn.setEnabled(False)
            self.panel.parent_combo.setEnabled(True)
            self.panel.child_combo.setEnabled(True)
            self.face_window = FaceQRWidget()
            self.face_window.face_qr.setPixmap(self.qpixmap_from_str(
                config.stream_status["face_url"]
            ))
            auth_worker = FaceAuthWorker(self.face_window)
            self.face_window.destroyed.connect(auth_worker.stop)
            self.add_thread(auth_worker)
            self.face_window.show()


# Entry point
if __name__ == '__main__':
    if MainWindow.is_another_instance_running():
        sys.exit(0)
    enable_hi_dpi()
    app = QApplication(sys.argv)
    setup_theme("auto")
    window = MainWindow()
    app.aboutToQuit.connect(window.on_exit)
    window.show()
    sys.exit(app.exec())
