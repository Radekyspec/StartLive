# module import
from contextlib import suppress
from functools import partial
from os.path import join, abspath
from traceback import format_exception
from typing import Optional, Callable

# package import
from PIL import ImageQt
from PySide6.QtCore import (QEvent, Qt, QTimer, QThreadPool, QUrl, Slot)
from PySide6.QtGui import QAction, QPixmap, QIcon, QActionGroup, \
    QDesktopServices
from PySide6.QtWidgets import (QLabel, QMessageBox, QVBoxLayout, QWidget,
                               QApplication, QSystemTrayIcon, QMenu,
                               QStackedWidget, QButtonGroup, QHBoxLayout
                               )
from darkdetect import isLight
from keyring import set_password, delete_password
from keyring.errors import PasswordDeleteError
from qdarktheme import setup_theme
from qrcode.main import QRCode

# local package import
import app_state
from app_state import dumps
from constant import *
from models.classes import ClickableLabel, SingleInstanceWindow
from models.log import init_logger, get_logger, get_log_path
from models.states import LoginState
from models.widgets import *
from models.window import *
from models.window.settings_page import SettingsPage
from models.window.stream_config import StreamConfigPanel
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

    def __init__(self, host, port, first_run, no_const_update, /, *,
                 base_path: str):
        super().__init__()
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        _, gui_handler = init_logger()
        self._log_viewer = LogViewer(self)
        gui_handler.recordUpdated.connect(self._log_viewer.append_line)
        self.logger = get_logger(self.__class__.__name__)
        self.logger.info(f"App {VERSION} created with host={host}, port={port}")
        self._host = host
        self._port = port
        self._cred_deleted = False
        self._no_const_update = no_const_update
        self._base_path = base_path
        self._base_title = f"StartLive 开播器 {VERSION}"
        self._server_started = False
        self._new_version_str = None

        self._thread_pool = QThreadPool()
        self._current_cookie_idx = 0
        self._cookie_index_len = len(
            CredentialManagerWorker.get_cookie_indices())
        self._managed_workers = []
        # Long live workers
        self._ll_workers = []
        self._worker_typeset = set()
        self.logger.info("Thread Pool initialized.")
        self.setWindowTitle(self._base_title)
        self._color_scheme = None
        self._stack = QStackedWidget(self)
        self._side_bar = SideBar(self, expanded_width=100, collapsed_width=56,
                                 icon_path=join(self._base_path, "resources"))
        btn_group = QButtonGroup(self)
        btn_group.setExclusive(True)
        btn_group.addButton(self._side_bar.btn_theme)
        self._side_bar.btn_theme.clicked.connect(self._change_color_scheme)
        mapping = [
            (self._side_bar.btn_home, 1),
            (self._side_bar.btn_log, 2),
            (self._side_bar.btn_settings, 3),
        ]
        for btn, idx in mapping:
            btn_group.addButton(btn)
            btn.clicked.connect(
                lambda _=False, i=idx: self._stack_switch(i))
        self._side_bar.btn_home.setChecked(True)
        self._settings_page = SettingsPage(self)
        self.setGeometry(300, 200, 610, 470)
        self.tray_icon = QSystemTrayIcon(self)
        # https://nuitka.net/user-documentation/common-issue-solutions.html#onefile-finding-files
        if app_state.app_settings["custom_tray_icon"]:
            self.tray_icon.setIcon(QIcon(
                abspath(app_state.app_settings["custom_tray_icon"])))
        else:
            self.tray_icon.setIcon(QIcon(
                join(self._base_path, "resources",
                     "icon_left.ico")))
        if app_state.app_settings["custom_tray_hint"]:
            self.tray_icon.setToolTip(
                app_state.app_settings["custom_tray_hint"])
        else:
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

        self._tools_menu = QMenu("文件", self)
        _open_log_folder_action = QAction("显示日志文件", self)
        _open_log_folder_action.triggered.connect(self._open_log_folder)
        self._tools_menu.addAction(_open_log_folder_action)
        menu_bar.addMenu(self._tools_menu)

        self._setting_menu = QMenu("缓存设置", self)
        menu_bar.addMenu(self._setting_menu)

        delete_cookies_action = QAction("退出账号登录", self)
        delete_cookies_action.triggered.connect(self._delete_cookies)
        self._setting_menu.addAction(delete_cookies_action)

        delete_settings_action = QAction("清除OBS连接设置", self)
        delete_settings_action.triggered.connect(self._delete_settings)
        self._setting_menu.addAction(delete_settings_action)

        delete_app_settings = QAction("清除APP设置", self)
        delete_app_settings.triggered.connect(self._delete_app_settings)
        self._setting_menu.addAction(delete_app_settings)

        delete_cred = QAction("清空所有凭据", self)
        delete_cred.triggered.connect(self._delete_cred)
        self._setting_menu.addAction(delete_cred)

        self.account_menu = QMenu("账号切换", self)
        menu_bar.addMenu(self.account_menu)
        self.account_menu.aboutToShow.connect(self._populate_account_menu)
        self._populate_account_menu()

        # self.proxy_menu = QMenu("代理设置", self)
        # menu_bar.addMenu(self.proxy_menu)
        # # self.proxy_menu.aboutToShow.connect(self._populate_proxy_menu)
        # proxy_group = QActionGroup(
        #     self,
        #     exclusionPolicy=QActionGroup.ExclusionPolicy.Exclusive
        # )
        # proxy_group.triggered.connect(self._switch_proxy)
        # no_proxy = QAction("不使用代理", self, checkable=True)
        # no_proxy.setData(False)
        # proxy_group.addAction(no_proxy)
        # self.proxy_menu.addAction(no_proxy)
        # system_proxy = QAction("使用系统代理", self, checkable=True)
        # system_proxy.setData(True)
        # proxy_group.addAction(system_proxy)
        # self.proxy_menu.addAction(system_proxy)
        # if config.app_settings["use_proxy"]:
        #     system_proxy.setChecked(True)
        # else:
        #     no_proxy.setChecked(True)
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
        if app_state.obs_client is not None:
            ObsDaemonWorker.disconnect_obs(self.panel.obs_btn_state)
        if self.panel is not None:
            self.tray_start_live_action.triggered.disconnect(
                self.panel.start_live)
            self.tray_stop_live_action.triggered.disconnect(
                self.panel.stop_live)

        self.tray_start_live_action.setEnabled(True)
        self.tray_stop_live_action.setEnabled(False)
        self._login_state = LoginState()
        self.panel = StreamConfigPanel(self)
        self.tray_start_live_action.triggered.connect(self.panel.start_live)
        self.tray_stop_live_action.triggered.connect(self.panel.stop_live)
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
        self._login_state.versionChecked.connect(self._new_version_hint)

        self.logger.info("StreamConfig initialized.")
        if self._no_const_update:
            self.logger.info("Constant update disabled.")
            app_state.scan_status["const_updated"] = True
        elif not app_state.scan_status["const_updated"]:
            const_updater = ConstantUpdateWorker(self._login_state)
            self.add_thread(const_updater,
                            on_finished=const_updater.on_finished)
            version_check = VersionCheckerWorker(self._login_state)
            self.add_thread(version_check,
                            on_finished=version_check.on_finished)
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

        login_widget = QWidget(self)
        login_widget.setLayout(layout)
        # self.setCentralWidget(central)
        if (w := self._stack.widget(WidgetIndex.WIDGET_LOGIN)) is not None:
            self._stack.removeWidget(w)
        self._stack.insertWidget(WidgetIndex.WIDGET_LOGIN, login_widget)
        if (w := self._stack.widget(WidgetIndex.WIDGET_PANEL)) is not None:
            self._stack.removeWidget(w)
        self._stack.insertWidget(WidgetIndex.WIDGET_PANEL, self.panel)
        if self._stack.indexOf(self._log_viewer) == -1:
            self._stack.insertWidget(WidgetIndex.WIDGET_LOGGING,
                                     self._log_viewer)
        if self._stack.indexOf(self._settings_page) == -1:
            self._stack.insertWidget(WidgetIndex.WIDGET_SETTINGS,
                                     self._settings_page)
        self._stack.setCurrentIndex(WidgetIndex.WIDGET_LOGIN)
        self._stack.currentChanged.connect(self._on_settings_loaded)
        self._side_bar.btn_home.setChecked(True)

        central = QWidget(self)
        root = QHBoxLayout()
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._side_bar)
        root.addWidget(self._stack, 1)
        central.setLayout(root)
        self.setCentralWidget(central)
        self.logger.info("Main UI initialized.")

        # Start fetching QR and begin polling thread
        self.credential_worker = CredentialManagerWorker(
            self._current_cookie_idx, is_new)
        self.login_worker = None
        self.add_thread(self.credential_worker,
                        on_finished=partial(self.credential_worker.on_finished,
                                            self, self._login_state))

        self.face_window: Optional[FaceQRWidget] = None

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
            self._server_started = True
            self._rebuild_title()

    def _stop_http_server(self):
        """This function should only be called once
        when the program is shutting down."""
        if self._server_thread is not None and self._server_started:
            self.logger.info("Stopping web server.")
            self._server_thread.stop()
            self._server_thread.quit()
            self._server_started = False
            self._rebuild_title()

    @Slot(Exception)
    def _http_error_handler(self, e: Exception):
        QMessageBox.critical(self, f"Web服务线程错误",
                             repr(e))
        self._stop_http_server()

    @Slot(str)
    def _new_version_hint(self, new_version: str):
        self._new_version_str = new_version
        self._rebuild_title()

    def _rebuild_title(self):
        if self._new_version_str:
            _new_version_title = f"有新版本可用: {self._new_version_str} - "
        else:
            _new_version_title = ""
        if self._server_started:
            _web_server_title = " - Web服务已开启"
        else:
            _web_server_title = ""
        self.setWindowTitle(
            f"{_new_version_title}{self._base_title}{_web_server_title}")

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
        if app_state.obs_settings.internal:
            self.logger.info("Saving OBS connection settings.")
            set_password(KEYRING_SERVICE_NAME, KEYRING_SETTINGS,
                         dumps(app_state.obs_settings.internal))
        if app_state.app_settings.internal:
            self.logger.info("Saving app settings.")
            set_password(KEYRING_SERVICE_NAME, KEYRING_APP_SETTINGS,
                         dumps(app_state.app_settings.internal))
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

    @Slot(int)
    def _on_settings_loaded(self, index: int):
        if index != WidgetIndex.WIDGET_SETTINGS:
            return
        if not self._ready_switch_account():
            return
        self._settings_page.delay_edit.setText("")
        fetch_delay = FetchStreamTimeShiftWorker()
        self.add_thread(fetch_delay,
                        on_finished=partial(fetch_delay.on_finished,
                                            self._settings_page.delay_edit))

    @staticmethod
    @Slot()
    def _open_log_folder():
        log_dir, _ = get_log_path(is_makedir=False)
        QDesktopServices.openUrl(QUrl.fromLocalFile(log_dir))

    @Slot()
    def _delete_cookies(self):
        if not app_state.scan_status["scanned"]:
            return
        cookie_index = CredentialManagerWorker.get_cookie_indices()
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

    @Slot()
    def _delete_settings(self):
        with suppress(PasswordDeleteError):
            delete_password(KEYRING_SERVICE_NAME, KEYRING_SETTINGS)
        self.panel.reset_obs_settings()
        QMessageBox.information(self, "设置清空", "OBS连接设置清除成功")

    @Slot()
    def _delete_app_settings(self):
        with suppress(PasswordDeleteError):
            delete_password(KEYRING_SERVICE_NAME, KEYRING_APP_SETTINGS)
        app_state.app_settings_default()
        self._settings_page.reset_default()
        self.tray_icon.setIcon(QIcon(
            join(self._base_path, "resources",
                 "icon_left.ico")))
        self.tray_icon.setToolTip("你所热爱的 就是你的生活")
        QMessageBox.information(self, "设置清空", "APP设置清除成功\n"
                                                  "字体相关设置需要重启生效")

    @Slot()
    def _delete_cred(self):
        with suppress(PasswordDeleteError):
            delete_password(KEYRING_SERVICE_NAME, KEYRING_SETTINGS)
        for cookie in CredentialManagerWorker.get_cookie_indices():
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

    @Slot()
    def _switch_account(self, action: QAction):
        idx = action.data()
        self.logger.info(f"select account index: {idx}")
        if idx == self._cookie_index_len or not self._ready_switch_account():
            return
        elif idx != self._current_cookie_idx:
            self._current_cookie_idx = idx
            CredentialManagerWorker.reset_default()
            self.setup_ui()

    def _ready_switch_account(self):
        """
        Determines whether the system is ready to switch the account based on the current
        cookie index or the scanning status configuration.

        This function evaluates multiple conditions, including whether all required
        scanning-related flags are updated to decide if switching accounts is feasible.

        If an error occurs during the scan, the function returns True to allow retrying.

        :return: A boolean indicating if the system is ready to switch accounts.
        :rtype: bool
        """
        return self._current_cookie_idx == self._cookie_index_len or all(
            [app_state.scan_status["scanned"],
             app_state.scan_status["area_updated"],
             app_state.scan_status["room_updated"],
             app_state.scan_status["const_updated"],
             app_state.scan_status["announce_updated"]
             ]) or (app_state.scan_status["cred_loaded"] and not
        app_state.scan_status["expired"] and not app_state.scan_status[
            "scanned"])

    @Slot()
    def _populate_account_menu(self):
        self.account_menu.clear()
        self.account_group = QActionGroup(self,
                                          exclusionPolicy=QActionGroup.ExclusionPolicy.Exclusive)
        self.account_group.triggered.connect(self._switch_account)

        cookie_indices = app_state.cookie_indices
        self._cookie_index_len = len(cookie_indices)
        self.logger.info(f"cookie index length: {self._cookie_index_len}")
        for idx, cookie_index in enumerate(cookie_indices):
            act = QAction(app_state.usernames.get(cookie_index, cookie_index),
                          self, checkable=True)
            act.setData(idx)
            self.account_group.addAction(act)
            self.account_menu.addAction(act)
            if idx == self._current_cookie_idx:
                act.setChecked(True)
        self.account_menu.addSeparator()
        add_new_account = QAction("添加新账号", self)
        add_new_account.triggered.connect(self._add_new_account)
        self.account_menu.addAction(add_new_account)

    @Slot()
    def _populate_tray_menu(self):
        cookie_indices = app_state.cookie_indices
        self._cookie_index_len = len(cookie_indices)
        if self._current_cookie_idx == self._cookie_index_len:
            self.tray_curr_user.setText("当前账号未登录")
            self.tray_curr_user.setEnabled(False)
            return
        self.tray_curr_user.setText(
            f"当前账号：{app_state.usernames[cookie_indices[self._current_cookie_idx]]}")
        self.tray_curr_user.setEnabled(True)

    def _add_new_account(self):
        if self._cookie_index_len == 0 or self._current_cookie_idx == self._cookie_index_len:
            return
        self._current_cookie_idx = self._cookie_index_len
        CredentialManagerWorker.reset_default()
        self.setup_ui(is_new=True)

    @Slot(str)
    def switch_tray_icon(self, icon_path: str):
        app_state.app_settings["custom_tray_icon"] = icon_path
        self.tray_icon.setIcon(QIcon(icon_path))

    def switch_tray_hint(self, hint: str):
        app_state.app_settings["custom_tray_hint"] = hint
        self.tray_icon.setToolTip(hint)

    @Slot()
    def load_credentials(self):
        app_state.scan_status["cred_loaded"] = True
        if app_state.scan_status["scanned"]:
            self._post_scan_setup()
        elif app_state.scan_status["expired"] or app_state.scan_status[
            "is_new"]:
            # Needs update credential
            self._fetch_qr()
        else:
            self.login_label.setText("登录时发生错误！请重试...")

    def _fetch_qr(self, retry: bool = False):
        # Start fetching QR and begin polling thread
        self.logger.info("Starting login flow.")
        app_state.scan_status["timeout"] = False
        if retry and self.login_worker is not None:
            self.status_label.clicked.disconnect(self._refresh_qr)
            self.login_worker.stop()
            # Reset status
            app_state.scan_status.update({
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

    @Slot()
    def _refresh_qr(self):
        self.update_qr_image("")
        self._fetch_qr(True)

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
        if not qr_url:
            self.qr_label.clear()
            return
        self.qr_label.setPixmap(self._qpixmap_from_str(qr_url))  # Show in UI

    def _after_login_success(self):
        self.panel.parent_combo.clear()
        self.panel.parent_combo.addItems(app_state.parent_area)
        self._stack.setCurrentIndex(1)
        self._side_bar.btn_home.setChecked(True)
        if app_state.obs_settings.get("auto_connect", False):
            self.panel.connect_btn.click()
        self.panel.parent_combo.setCurrentText(
            app_state.room_info.get("parent_area", "请选择"))
        self.panel.child_combo.setCurrentText(
            app_state.room_info.get("area", ""))
        self.panel.enable_child_combo_autosave(True)
        self._start_http_server()

    @Slot()
    def _post_scan_setup(self):
        if not app_state.scan_status["scanned"]:
            return
        if self.status_label.text() != "登录成功！":
            self.status_label.setText("登录成功！")
            self.status_label.setStyleSheet("color: green;font-size: 16pt;")
        if app_state.scan_status["area_updated"]:
            login_hint1 = "分区已更新！"
        else:
            login_hint1 = "正在更新分区..."
        if app_state.scan_status["room_updated"] and app_state.scan_status[
            "announce_updated"]:
            login_hint2 = "房间信息已更新！"
        else:
            login_hint2 = "正在更新房间信息..."
        if app_state.scan_status["const_updated"]:
            login_hint3 = "请求参数已更新！"
        else:
            login_hint3 = "正在更新请求参数..."
        login_hint = f"{login_hint1}\n{login_hint2}\n{login_hint3}"
        self.login_label.setText(login_hint)
        if not app_state.scan_status["area_updated"] or \
                not app_state.scan_status["room_updated"] or \
                not app_state.scan_status["const_updated"] or \
                not app_state.scan_status["announce_updated"]:
            return
        self._after_login_success()

    @Slot()
    def _qr_expired(self):
        self.status_label.setText("二维码已失效，点击这里刷新")
        self.status_label.setStyleSheet("color: red; font-size: 16pt;")
        self.status_label.clicked.connect(self._refresh_qr)

    @Slot()
    def _qr_not_confirmed(self):
        self.status_label.setText("已扫码，等待确认登录...")

    def popup_face_widget(self, face_url: str):
        app_state.stream_status["required_face"] = False
        self.panel.start_btn.setEnabled(True)
        self.tray_start_live_action.setEnabled(True)
        self.panel.stop_btn.setEnabled(False)
        self.tray_stop_live_action.setEnabled(False)
        self.panel.parent_combo.setEnabled(True)
        self.panel.child_combo.setEnabled(True)
        auth_worker = FaceAuthWorker()
        self.face_window = FaceQRWidget(auth_worker)
        self.face_window.face_qr.setPixmap(self._qpixmap_from_str(face_url))
        self.add_thread(auth_worker,
                        on_finished=partial(auth_worker.on_finished,
                                            self.face_window))
        self.face_window.show()

    def apply_color_scheme(self, scheme: Qt.ColorScheme):
        self._color_scheme = scheme
        if scheme == Qt.ColorScheme.Light:
            self._apply_light_scheme()
        else:
            self._apply_dark_scheme()

    def _apply_dark_scheme(self):
        setup_theme("dark", additional_qss=DARK_CSS)
        self._side_bar.apply_dark_mode()

    def _apply_light_scheme(self):
        setup_theme("light", additional_qss=LIGHT_CSS)
        self._side_bar.apply_light_mode()

    def _change_color_scheme(self):
        scheme = self._color_scheme
        if scheme == Qt.ColorScheme.Dark:
            self._color_scheme = Qt.ColorScheme.Light
            self._apply_light_scheme()
        else:
            self._color_scheme = Qt.ColorScheme.Dark
            self._apply_dark_scheme()

    def _stack_switch(self, i: int):
        if i == 1 and not app_state.scan_status["scanned"]:
            self._stack.setCurrentIndex(0)
            return
        self._stack.setCurrentIndex(i)
