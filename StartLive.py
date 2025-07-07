# -*- coding: utf-8 -*-

# module import
import os.path
import sys
from argparse import ArgumentParser
from contextlib import suppress
from functools import partial
from platform import system
from subprocess import Popen
from traceback import format_exception
from typing import Optional, Callable

# package import
from PIL import ImageQt
from PySide6.QtCore import (QEvent, Qt, QTimer, QThreadPool)
from PySide6.QtGui import QAction, QPixmap, QIcon
from PySide6.QtWidgets import (QLabel, QMessageBox, QVBoxLayout, QWidget,
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
from models.classes import ClickableLabel, SingleInstanceWindow
from models.log import init_logger, get_logger
from models.widgets import *
from models.workers import *
from models.workers.base import *


# Main GUI window
class MainWindow(SingleInstanceWindow):
    _managed_workers: list[BaseWorker | LongLiveWorker]
    _ll_workers: list[LongLiveWorker]

    def __init__(self, host, port):
        super().__init__()
        init_logger()
        self.logger = get_logger(self.__class__.__name__)
        self.logger.info(f"App created with host={host}, port={port}")
        self._base_interval = 200
        self._worker_interval = 200
        self._max_interval = 10000
        self._thread_pool = QThreadPool()
        self._managed_workers = []
        self.timer = QTimer()
        # Long live workers
        self._ll_workers = []
        self.logger.info("Thread Pool initialized.")
        self.setWindowTitle(f"StartLive 开播器 {VERSION}")
        self.windowTitle()
        self.setGeometry(300, 200, 520, 430)
        self.tray_icon = QSystemTrayIcon(self)
        # https://nuitka.net/user-documentation/common-issue-solutions.html#onefile-finding-files
        self.tray_icon.setIcon(QIcon(
            os.path.join(os.path.dirname(__file__), "resources",
                         "icon_cr.png")))
        self.tray_icon.setToolTip("你所热爱的 就是你的生活")
        self.tray_icon.setVisible(True)
        self.logger.info("System tray icon initialized.")
        self.add_thread(ConstantUpdateWorker(), on_finished=ConstantUpdateWorker.on_finished)

        tray_menu = QMenu()
        restore_action = QAction("显示窗口", self)
        quit_action = QAction("退出", self)
        tray_menu.addAction(restore_action)
        tray_menu.addAction(quit_action)
        self.tray_icon.setContextMenu(tray_menu)
        restore_action.triggered.connect(self.show_normal)
        quit_action.triggered.connect(QApplication.quit)
        self.tray_icon.activated.connect(self.on_tray_icon_activated)
        self.logger.info("Tray menu initialized.")

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

        delete_cred = QAction("清空所有凭据", self)
        delete_cred.triggered.connect(self._delete_cred)
        setting_menu.addAction(delete_cred)

        self.logger.info("Menu bar initialized.")

        # Widgets for login phase
        self.login_label = QLabel("正在获取保存的登录凭证...")
        self.status_label = ClickableLabel("等待登录中...")
        self.qr_label = QLabel()
        self.panel = StreamConfigPanel(self, host, port)
        self.logger.info("StreamConfig initialized.")

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
        self.logger.info("Main QR layout initialized.")

        # Start fetching QR and begin polling thread
        self.credential_worker = CredentialManagerWorker()
        self.login_worker = None
        self.add_thread(self.credential_worker,
                        on_finished=partial(self.credential_worker.on_finished, self))

        self.face_window: Optional[FaceQRWidget] = None

    def changeEvent(self, event):
        if event.type() == QEvent.Type.WindowStateChange:
            if self.isMinimized():
                QTimer.singleShot(0, self.hide)  # 延迟隐藏窗口
        super().changeEvent(event)

    def closeEvent(self, event):
        # 关闭窗口时退出应用
        self.panel.stop_server()
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
        if not config.scan_status["scanned"]:
            return
        del config.room_info["parent_area"]
        del config.room_info["area"]
        set_password(KEYRING_SERVICE_NAME, KEYRING_ROOM_INFO,
                     dumps(config.room_info.internal))
        QMessageBox.information(self, "分区缓存清空", "分区缓存清除成功")

    def _delete_cred(self):
        with suppress(PasswordDeleteError):
            delete_password(KEYRING_SERVICE_NAME, KEYRING_COOKIES)
        with suppress(PasswordDeleteError):
            delete_password(KEYRING_SERVICE_NAME, KEYRING_SETTINGS)
        with suppress(PasswordDeleteError):
            delete_password(KEYRING_SERVICE_NAME, KEYRING_ROOM_INFO)
        QMessageBox.information(self, "凭据清空",
                                "已清空全部凭据, 程序即将退出")
        for worker in self._ll_workers:
            worker.stop()
        sys.exit(0)

    def fetch_qr(self, retry=False):
        # Start fetching QR and begin polling thread
        self.logger.info("Starting login flow.")
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
            self.timer.start(50)
        qr_login_worker = QRLoginWorker()
        self.add_thread(qr_login_worker,
                        on_finished=partial(qr_login_worker.on_finished, self))
        self.login_worker = FetchLoginWorker()
        self.add_thread(self.login_worker,
                        on_finished=partial(self.login_worker.on_finished, self))
        self.login_label.setText("请使用手机扫码登录：")
        self.status_label.setText("等待扫码中...")
        self.status_label.setStyleSheet("color: blue; font-size: 16pt;")
        # Timer checks the login state and updates UI

    def load_credentials(self):
        self.timer.timeout.connect(self.check_scan_status)
        self.timer.start(50)
        if not config.scan_status["scanned"]:
            # Needs update credential
            self.fetch_qr()

    def add_thread(self, worker: BaseWorker | LongLiveWorker, *,
                   on_finished: Callable | None = None,
                   on_exception: Callable | None = None):
        if on_finished is not None:
            worker.signals.finished.connect(on_finished)
        worker.signals.finished.connect(partial(self._remove_worker, worker))
        if on_exception is not None:
            worker.signals.exception.connect(on_exception)
        worker.signals.exception.connect(partial(self._worker_exception, worker))
        self.logger.info(f"{worker.__class__.__name__} added to thread pool")
        self._managed_workers.append(worker)
        if isinstance(worker, LongLiveWorker):
            self._ll_workers.append(worker)
        self._thread_pool.start(worker)

    def _remove_worker(self, dead_worker: BaseWorker | LongLiveWorker):
        self.logger.info(
            f"{dead_worker.__class__.__name__} removed from thread pool")
        self._managed_workers.remove(dead_worker)
        if dead_worker in self._ll_workers:
            self._ll_workers.remove(dead_worker)

    def _worker_exception(self, worker: BaseWorker | LongLiveWorker,
                          e: Exception):
        self.logger.error(
            format_exception(type(e), e, e.__traceback__))
        QMessageBox.critical(self, f"{worker.name}线程错误",
                             repr(e))

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
        self.panel.start_server()

    def check_scan_status(self):
        if config.scan_status["scanned"]:
            # Login succeeded, ready to switch to main UI
            if self.status_label.text() != "登录成功！":
                self.status_label.setText("登录成功！")
                self.status_label.setStyleSheet("color: green;font-size: 16pt;")
            if config.scan_status["area_updated"]:
                login_hint1 = "分区已更新！"
            else:
                login_hint1 = "正在更新分区..."
            if config.scan_status["room_updated"]:
                login_hint2 = "房间信息已更新！"
            else:
                login_hint2 = "正在更新房间信息..."
            if config.scan_status["const_updated"]:
                login_hint3 = "请求参数已更新！"
            else:
                login_hint3 = "正在更新请求参数..."
            login_hint = f"{login_hint1}\n{login_hint2}\n{login_hint3}"
            self.login_label.setText(login_hint)
            if not config.scan_status["area_updated"] or \
                    not config.scan_status["room_updated"] or \
                    not config.scan_status["const_updated"]:
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
            self.add_thread(auth_worker,
                            on_finished=partial(auth_worker.on_finished, self.face_window))
            self.face_window.show()


# Entry point
if __name__ == '__main__':
    if MainWindow.is_another_instance_running():
        sys.exit(0)
    if system() == "Windows":
        try:
            updater_path = os.path.abspath(os.path.join(
                __compiled__.containing_dir, "Update.exe"))
            if os.path.exists(updater_path):
                Popen([updater_path, "--update=https://startlive.vtbs.ai/"])
        except:
            pass
    parser = ArgumentParser()

    parser.add_argument("--web.host", dest="web_host", default=None,
                        help="Web服务绑定的主机地址")

    parser.add_argument("--web.port", dest="web_port", type=int, default=None,
                        help="Web服务绑定的端口")

    args, qt_args = parser.parse_known_args()
    enable_hi_dpi()
    app = QApplication(qt_args)
    setup_theme("auto")
    window = MainWindow(args.web_host, args.web_port)
    app.aboutToQuit.connect(window.on_exit)
    window.show()
    sys.exit(app.exec())
