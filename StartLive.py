# -*- coding: utf-8 -*-

# module import
import sys
from argparse import ArgumentParser
from contextlib import suppress
from functools import partial
from os.path import abspath, dirname, join, isdir, exists
from platform import system
from subprocess import Popen
from traceback import format_exception
from typing import Optional, Callable

import darkdetect
# package import
from PIL import ImageQt
from PySide6.QtCore import (QEvent, Qt, QTimer, QThreadPool, QUrl, Slot)
from PySide6.QtGui import QAction, QPixmap, QIcon, QActionGroup, \
    QDesktopServices, QFont, QPalette, QGuiApplication
from PySide6.QtWidgets import (QLabel, QMessageBox, QVBoxLayout, QWidget,
                               QApplication, QSystemTrayIcon, QMenu
                               )
from darkdetect import isLight
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
from models.log import init_logger, get_logger, get_log_path
from models.states import LoginState
from models.widgets import *
from models.workers import *
from models.workers.base import *
from web_server import HttpServerWorker


# Main GUI window
class MainWindow(SingleInstanceWindow):
    _managed_workers: list[BaseWorker | LongLiveWorker]
    _worker_typeset: set[str]
    _ll_workers: list[LongLiveWorker]
    _thread_pool: QThreadPool
    _host: str
    _port: int
    _cred_deleted: bool
    _no_const_update: bool
    _server_started: bool
    _server_thread: Optional[HttpServerWorker]
    _current_cookie_idx: int
    _cookie_index_len: int
    _login_state: LoginState
    account_group: QActionGroup
    account_menu: QMenu
    login_label: QLabel
    status_label: ClickableLabel
    qr_label: QLabel
    panel: StreamConfigPanel | None
    credential_worker: CredentialManagerWorker
    login_worker: Optional[FetchLoginWorker]
    face_window: Optional[FaceQRWidget]
    tray_start_live_action: QAction
    tray_stop_live_action: QAction

    def __init__(self, host, port, first_run, no_const_update, /):
        super().__init__()
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        init_logger()
        self.logger = get_logger(self.__class__.__name__)
        self.logger.info(f"App created with host={host}, port={port}")
        self._host = host
        self._port = port
        self._cred_deleted = False
        self._no_const_update = no_const_update
        self._thread_pool = QThreadPool()
        self._current_cookie_idx = 0
        self._cookie_index_len = len(
            CredentialManagerWorker.get_cookies_index())
        self._managed_workers = []
        # Long live workers
        self._ll_workers = []
        self._worker_typeset = set()
        self.logger.info("Thread Pool initialized.")
        self.setWindowTitle(f"StartLive 开播器 {VERSION}")
        self.windowTitle()
        self.setGeometry(300, 200, 520, 470)
        self.tray_icon = QSystemTrayIcon(self)
        # https://nuitka.net/user-documentation/common-issue-solutions.html#onefile-finding-files
        self.tray_icon.setIcon(QIcon(
            join(dirname(__file__), "resources",
                 "icon_cr.png")))
        self.tray_icon.setToolTip("你所热爱的 就是你的生活")
        self.tray_icon.setVisible(True)
        self.logger.info("System tray icon initialized.")

        tray_menu = QMenu()
        restore_action = QAction("显示窗口", self)
        self.tray_curr_user = QAction("", self)
        self.tray_start_live_action = QAction("开始直播", self)
        self.tray_stop_live_action = QAction("停止直播", self)
        self.tray_stop_live_action.setEnabled(False)
        quit_action = QAction("退出", self)
        tray_menu.addAction(restore_action)
        tray_menu.addAction(self.tray_curr_user)
        tray_menu.addSeparator()
        tray_menu.addAction(self.tray_start_live_action)
        tray_menu.addAction(self.tray_stop_live_action)
        tray_menu.addSeparator()
        tray_menu.addAction(quit_action)
        tray_menu.aboutToShow.connect(self._populate_tray_menu)
        self.tray_icon.setContextMenu(tray_menu)
        restore_action.triggered.connect(self._show_normal)
        quit_action.triggered.connect(QApplication.quit)
        self.tray_icon.activated.connect(self._on_tray_icon_activated)
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

        delete_cred = QAction("清空所有凭据", self)
        delete_cred.triggered.connect(self._delete_cred)
        setting_menu.addAction(delete_cred)

        open_log_folder = QAction("显示日志文件", self)
        open_log_folder.triggered.connect(self._open_log_folder)
        menu_bar.addAction(open_log_folder)

        self.account_menu = QMenu("账号切换", self)
        menu_bar.addMenu(self.account_menu)
        self.account_menu.aboutToShow.connect(self._populate_account_menu)

        self.proxy_menu = QMenu("代理设置", self)
        menu_bar.addMenu(self.proxy_menu)
        # self.proxy_menu.aboutToShow.connect(self._populate_proxy_menu)
        proxy_group = QActionGroup(
            self,
            exclusionPolicy=QActionGroup.ExclusionPolicy.Exclusive
        )
        proxy_group.triggered.connect(self._switch_proxy)
        no_proxy = QAction("不使用代理", self, checkable=True)
        no_proxy.setData(False)
        proxy_group.addAction(no_proxy)
        self.proxy_menu.addAction(no_proxy)
        system_proxy = QAction("使用系统代理", self, checkable=True)
        system_proxy.setData(True)
        proxy_group.addAction(system_proxy)
        self.proxy_menu.addAction(system_proxy)
        if config.app_settings["use_proxy"]:
            system_proxy.setChecked(True)
        else:
            no_proxy.setChecked(True)
        self.logger.info("Menu bar initialized.")

        if first_run:
            QMessageBox.information(self, "安装完成",
                                    f"StartLive开播器 版本{VERSION} 安装成功\n"
                                    "之后再运行请使用桌面或开始菜单里的快捷方式。")
        # Widgets for login phase
        self.panel = None
        self.setup_ui()
        self._init_http_server()

    def setup_ui(self, *, is_new: bool = False):
        for worker in self._ll_workers:
            worker.stop()
        if config.obs_client is not None:
            ObsDaemonWorker.disconnect_obs(self.panel.obs_btn_state)
        if self.panel is not None:
            self.tray_start_live_action.triggered.disconnect(
                self.panel.start_live)
            self.tray_stop_live_action.triggered.disconnect(
                self.panel.stop_live)

        self._login_state = LoginState()
        self.panel = StreamConfigPanel(self)
        self.tray_start_live_action.triggered.connect(self.panel.start_live)
        self.tray_stop_live_action.triggered.connect(self.panel.stop_live)
        config.session.headers.clear()
        config.session.headers.update(constant.HEADERS_WEB)
        self.login_label = QLabel("正在获取保存的登录凭证...")
        self.status_label = ClickableLabel("等待登录中...")
        self.qr_label = QLabel()
        self._login_state.areaUpdated.connect(self._post_scan_setup)
        self._login_state.constUpdated.connect(self._post_scan_setup)
        self._login_state.credentialLoaded.connect(self.load_credentials)
        self._login_state.roomUpdated.connect(self._post_scan_setup)
        self._login_state.qrScanned.connect(self._post_scan_setup)
        self._login_state.qrExpired.connect(self._qr_expired)
        self._login_state.qrNotConfirmed.connect(self._qr_not_confirmed)

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
        self.credential_worker = CredentialManagerWorker(
            self._current_cookie_idx, is_new)
        self.login_worker = None
        self.add_thread(self.credential_worker,
                        on_finished=partial(self.credential_worker.on_finished,
                                            self, self._login_state))

        self.face_window: Optional[FaceQRWidget] = None
        if self._no_const_update:
            self.logger.info("Constant update disabled.")
            config.scan_status["const_updated"] = True
        else:
            const_updater = ConstantUpdateWorker(self._login_state)
            self.add_thread(const_updater,
                            on_finished=const_updater.on_finished)

    def _init_http_server(self):
        self._server_started = False
        if self._host is not None and self._port is not None:
            self._server_thread = HttpServerWorker(self._host, self._port)
            self._server_thread.signals.startLive.connect(self.panel.start_live)
            self._server_thread.signals.stopLive.connect(self.panel.stop_live)
            self._server_thread.signals.exception.connect(
                self._http_error_handler)
        else:
            self._server_thread = None

    def _start_http_server(self):
        if self._server_thread is not None and not self._server_started:
            self._server_thread.start()
            self.setWindowTitle(
                self.windowTitle() + " - Web服务已开启")
            self._server_started = True

    def _stop_http_server(self):
        """This function should only be called once
        when the program is shutting down."""
        if self._server_thread is not None and self._server_started:
            self.logger.info("Stopping web server.")
            self._server_thread.stop()
            self._server_thread.quit()
            self._server_started = False

    @Slot(Exception)
    def _http_error_handler(self, e: Exception):
        QMessageBox.critical(self, f"Web服务线程错误",
                             repr(e))
        self.setWindowTitle(f"StartLive 开播器 {VERSION}")
        self._stop_http_server()

    def changeEvent(self, event):
        if event.type() == QEvent.Type.WindowStateChange:
            if self.isMinimized():
                QTimer.singleShot(0, self.hide)  # 延迟隐藏窗口
        super().changeEvent(event)

    def closeEvent(self, event):
        # 关闭窗口时退出应用
        self.logger.info("closeEvent triggered. Exiting application.")
        if self._cred_deleted:
            self.logger.info("Credentials deleted. Exiting application.")
            event.accept()
            return
        if self.panel is not None:
            self.panel.stop_live()
        if config.obs_settings.internal:
            self.logger.info("Saving OBS connection settings.")
            set_password(KEYRING_SERVICE_NAME, KEYRING_SETTINGS,
                         dumps(config.obs_settings.internal))
        if config.app_settings.internal:
            self.logger.info("Saving app settings.")
            set_password(KEYRING_SERVICE_NAME, KEYRING_APP_SETTINGS,
                         dumps(config.app_settings.internal))
        for worker in self._ll_workers:
            worker.stop()
        self._stop_http_server()
        self.tray_icon.hide()
        self.tray_icon.deleteLater()
        QApplication.closeAllWindows()
        self.logger.info("Application closed.")
        event.accept()

    def _show_normal(self):
        self.show()
        self.setWindowState(Qt.WindowState.WindowActive)

    def _on_tray_icon_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self._show_normal()

    @staticmethod
    def _open_log_folder():
        log_dir, _ = get_log_path(is_makedir=False)
        QDesktopServices.openUrl(QUrl.fromLocalFile(log_dir))

    def _delete_cookies(self):
        if not config.scan_status["scanned"]:
            return
        cookie_index = CredentialManagerWorker.get_cookies_index()
        with suppress(PasswordDeleteError):
            delete_password(KEYRING_SERVICE_NAME,
                            cookie_index[self._current_cookie_idx])
        cookie_index.remove(cookie_index[self._current_cookie_idx])
        set_password(KEYRING_SERVICE_NAME, KEYRING_COOKIES_INDEX,
                     dumps(cookie_index))
        self._current_cookie_idx = max(0, self._current_cookie_idx - 1)
        self._populate_account_menu()
        CredentialManagerWorker.reset_default()
        QMessageBox.information(self, "账号退出", "账号退出成功")
        self.setup_ui(is_new=self._cookie_index_len == 0)

    def _delete_settings(self):
        with suppress(PasswordDeleteError):
            delete_password(KEYRING_SERVICE_NAME, KEYRING_SETTINGS)
        self.panel.reset_obs_settings()
        QMessageBox.information(self, "设置清空", "OBS连接设置清除成功")

    def _delete_cred(self):
        with suppress(PasswordDeleteError):
            delete_password(KEYRING_SERVICE_NAME, KEYRING_SETTINGS)
        for cookie in CredentialManagerWorker.get_cookies_index():
            with suppress(PasswordDeleteError):
                delete_password(KEYRING_SERVICE_NAME, cookie)
        with suppress(PasswordDeleteError):
            delete_password(KEYRING_SERVICE_NAME, KEYRING_COOKIES_INDEX)
        with suppress(PasswordDeleteError):
            delete_password(KEYRING_SERVICE_NAME, KEYRING_APP_SETTINGS)
        self._cred_deleted = True
        QMessageBox.information(self, "凭据清空",
                                "已清空全部凭据, 程序即将退出")
        for worker in self._ll_workers:
            worker.stop()
        QApplication.quit()

    def _switch_account(self, action: QAction):
        idx = action.data()
        self.logger.info(f"select account index: {idx}")
        if idx == self._cookie_index_len:
            return
        elif idx != self._current_cookie_idx:
            self._current_cookie_idx = idx
            CredentialManagerWorker.reset_default()
            self.setup_ui()

    def _populate_account_menu(self):
        self.account_menu.clear()
        self.account_group = QActionGroup(self,
                                          exclusionPolicy=QActionGroup.ExclusionPolicy.Exclusive)
        self.account_group.triggered.connect(self._switch_account)

        cookie_indices = CredentialManagerWorker.get_cookies_index()
        self._cookie_index_len = len(cookie_indices)
        self.logger.info(f"cookie index length: {self._cookie_index_len}")
        for idx, cookie_index in enumerate(cookie_indices):
            act = QAction(config.usernames[cookie_index], self, checkable=True)
            act.setData(idx)
            self.account_group.addAction(act)
            self.account_menu.addAction(act)
            if idx == self._current_cookie_idx:
                act.setChecked(True)
        self.account_menu.addSeparator()
        add_new_account = QAction("添加新账号", self)
        add_new_account.triggered.connect(self._add_new_account)
        self.account_menu.addAction(add_new_account)

    def _populate_tray_menu(self):
        if self._current_cookie_idx == self._cookie_index_len:
            self.tray_curr_user.setText("当前账号未登录")
            self.tray_curr_user.setEnabled(False)
            return
        cookie_indices = CredentialManagerWorker.get_cookies_index()
        self.tray_curr_user.setText(
            f"当前账号：{config.usernames[cookie_indices[self._current_cookie_idx]]}")
        self.tray_curr_user.setEnabled(True)

    def _add_new_account(self):
        if self._cookie_index_len == 0 or self._current_cookie_idx == self._cookie_index_len:
            return
        self._current_cookie_idx = self._cookie_index_len
        CredentialManagerWorker.reset_default()
        self.setup_ui(is_new=True)

    @staticmethod
    def _switch_proxy(action: QAction):
        use_proxy = action.data()
        config.app_settings["use_proxy"] = use_proxy
        if use_proxy:
            config.session.get = partial(config.session.get, verify=False)
            config.session.post = partial(config.session.post, verify=False)
            config.session.trust_env = True
        else:
            config.session.get = partial(config.session.get, verify=True)
            config.session.post = partial(config.session.post, verify=True)
            config.session.trust_env = False

    def load_credentials(self):
        if config.scan_status["scanned"]:
            self._post_scan_setup()
        else:
            # Needs update credential
            self._fetch_qr()

    def _fetch_qr(self, retry: bool = False):
        # Start fetching QR and begin polling thread
        self.logger.info("Starting login flow.")
        config.scan_status["timeout"] = False
        if retry and self.login_worker is not None:
            self.status_label.clicked.disconnect(self._fetch_qr)
            self.login_worker.stop()
            # Reset status
            config.scan_status.update({
                "qr_key": None, "qr_url": None,
                "wait_for_confirm": False
            })
        qr_login_worker = FetchQRWorker()
        self.add_thread(qr_login_worker,
                        on_finished=partial(qr_login_worker.on_finished, self))
        self.login_worker = FetchLoginWorker(self._login_state)
        self.add_thread(self.login_worker,
                        on_finished=partial(self.login_worker.on_finished,
                                            self))
        self.login_label.setText("请使用手机扫码登录：")
        self.status_label.setText("等待扫码中...")
        self.status_label.setStyleSheet("color: blue; font-size: 16pt;")
        # Timer checks the login state and updates UI

    def add_thread(self, worker: BaseWorker | LongLiveWorker, *,
                   on_finished: Callable | None = None,
                   on_exception: Callable | None = None):
        if worker.__class__.__name__ in self._worker_typeset:
            # Only one same-typed worker should run concurrently
            self.logger.warning(f"Attempting to add {worker.__class__.__name__}"
                                f" but one already exists.")
            return
        if on_finished is not None:
            worker.signals.finished.connect(on_finished)
        worker.signals.finished.connect(partial(self._remove_worker, worker))
        if on_exception is not None:
            worker.signals.exception.connect(on_exception)
        worker.signals.exception.connect(
            partial(self._worker_exception, worker))
        self.logger.info(f"{worker.__class__.__name__} added to thread pool")
        self._managed_workers.append(worker)
        self._worker_typeset.add(worker.__class__.__name__)
        if isinstance(worker, LongLiveWorker):
            self._ll_workers.append(worker)
        self._thread_pool.start(worker)

    @Slot()
    def _remove_worker(self, dead_worker: BaseWorker | LongLiveWorker):
        self.logger.info(
            f"{dead_worker.__class__.__name__} removed from thread pool")
        self._managed_workers.remove(dead_worker)
        self._worker_typeset.remove(dead_worker.__class__.__name__)
        if dead_worker in self._ll_workers:
            self._ll_workers.remove(dead_worker)

    @Slot()
    def _worker_exception(self, worker: BaseWorker | LongLiveWorker,
                          e: Exception):
        self.logger.error(
            format_exception(type(e), e, e.__traceback__))
        QMessageBox.critical(self, f"{worker.name}线程错误",
                             repr(e))

    @staticmethod
    # Helper: Generate QR code image from URL
    def generate_qr_code(data: str):
        qr = QRCode(box_size=4, border=1)
        qr.add_data(data)
        qr.make(fit=True)
        if isLight():
            img = qr.make_image(fill_color="black", back_color="white")
        else:
            img = qr.make_image(fill_color="white", back_color="black")
        return img.convert("RGB")

    @classmethod
    # Helper: Convert a PIL image to QPixmap for display in QLabel
    def _qpixmap_from_str(cls, data: str):
        return QPixmap.fromImage(ImageQt.ImageQt(cls.generate_qr_code(data)))

    def update_qr_image(self, qr_url: str):
        self.qr_label.setPixmap(self._qpixmap_from_str(qr_url))  # Show in UI

    def _after_login_success(self):
        config.session.headers.clear()
        config.session.headers.update(constant.HEADERS_APP)
        self.panel.parent_combo.clear()
        self.panel.parent_combo.addItems(config.parent_area)
        self.setCentralWidget(self.panel)
        if config.obs_settings.get("auto_connect", False):
            self.panel.connect_btn.click()
        self.panel.parent_combo.setCurrentText(
            config.room_info.get("parent_area", "请选择"))
        self.panel.child_combo.setCurrentText(
            config.room_info.get("area", ""))
        self._start_http_server()

    @Slot()
    def _post_scan_setup(self):
        if not config.scan_status["scanned"]:
            return
        if self.status_label.text() != "登录成功！":
            self.status_label.setText("登录成功！")
            self.status_label.setStyleSheet("color: green;font-size: 16pt;")
        if config.scan_status["area_updated"]:
            login_hint1 = "分区已更新！"
        else:
            login_hint1 = "正在更新分区..."
        if config.scan_status["room_updated"] and config.scan_status[
            "announce_updated"]:
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
                not config.scan_status["const_updated"] or \
                not config.scan_status["announce_updated"]:
            return
        self._after_login_success()

    @Slot()
    def _qr_expired(self):
        self.status_label.setText("二维码已失效，点击这里刷新")
        self.status_label.setStyleSheet("color: red; font-size: 16pt;")
        self.status_label.clicked.connect(lambda: self._fetch_qr(True))

    @Slot()
    def _qr_not_confirmed(self):
        self.status_label.setText("已扫码，等待确认登录...")

    def popup_face_widget(self, face_url: str):
        config.stream_status["required_face"] = False
        self.panel.start_btn.setEnabled(True)
        self.tray_start_live_action.setEnabled(True)
        self.panel.stop_btn.setEnabled(False)
        self.tray_stop_live_action.setEnabled(False)
        self.panel.parent_combo.setEnabled(True)
        self.panel.child_combo.setEnabled(True)
        self.face_window = FaceQRWidget()
        self.face_window.face_qr.setPixmap(self._qpixmap_from_str(face_url))
        auth_worker = FaceAuthWorker(self.face_window)
        self.face_window.destroyed.connect(auth_worker.stop)
        self.add_thread(auth_worker,
                        on_finished=partial(auth_worker.on_finished,
                                            self.face_window))
        self.face_window.show()

    @staticmethod
    def apply_color_scheme(scheme: Qt.ColorScheme):
        if scheme == Qt.ColorScheme.Light:
            setup_theme("light", additional_qss=LIGHT_CSS)
        elif scheme == Qt.ColorScheme.Dark:
            setup_theme("dark", additional_qss=DARK_CSS)
        else:
            setup_theme("light", additional_qss=LIGHT_CSS)

# Entry point
if __name__ == '__main__':
    if MainWindow.is_another_instance_running():
        sys.exit(0)
    if system() == "Windows":
        try:
            install_path = abspath(__compiled__.containing_dir)
            updater_path = join(install_path, "Update.exe")
            app_path = join(install_path, f"app-{VERSION}")
            if exists(updater_path) and isdir(app_path):
                Popen([updater_path, "--update=https://startlive.vtbs.ai/"])
        except NameError:
            pass
    parser = ArgumentParser()

    parser.add_argument("--web.host", dest="web_host", default=None,
                        help="Web服务绑定的主机地址")
    parser.add_argument("--web.port", dest="web_port", type=int, default=None,
                        help="Web服务绑定的端口")
    parser.add_argument("--squirrel-firstrun", dest="first_run",
                        action="store_true")
    parser.add_argument("--noupdate", dest="no_update",
                        action="store_true")

    args, qt_args = parser.parse_known_args()
    enable_hi_dpi()
    app = QApplication(qt_args)
    app.setFont(QFont(
        "Open Sans,.AppleSystemUIFont,Helvetica,Arial,MS Shell Dlg,sans-serif",
        9))
    MainWindow.apply_color_scheme(app.styleHints().colorScheme())
    app.styleHints().colorSchemeChanged.connect(MainWindow.apply_color_scheme)
    window = MainWindow(args.web_host, args.web_port, args.first_run,
                        args.no_update)
    window.show()
    sys.exit(app.exec())
