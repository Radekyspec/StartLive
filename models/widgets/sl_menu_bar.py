from contextlib import suppress
from shutil import rmtree

from PySide6.QtCore import Slot, QUrl, Signal
from PySide6.QtGui import QAction, QActionGroup, QDesktopServices
from PySide6.QtWidgets import QMenuBar, QMenu
from keyring import delete_password, set_password
from keyring.errors import PasswordDeleteError

import app_state
from app_state import dumps
from constant import *
from models.cache import cache_base_dir
from models.log import get_log_path, get_logger
from models.workers import CredentialManagerWorker


class StartLiveMenuBar(QMenuBar):
    cookieDeleted = Signal(int, bool, bool)
    obsSettingsDeleted = Signal()
    appSettingsDeleted = Signal()
    bgDeleted = Signal()
    credDeleted = Signal(bool)
    accountSwitch = Signal(int)
    accountAdded = Signal(int)
    accountMenuPopulated = Signal(int)

    def __init__(self, parent=None, /):
        super().__init__(parent)
        self.logger = get_logger(self.__class__.__name__)
        self._current_cookie_idx = 0
        self._cookie_index_len = len(
            CredentialManagerWorker.get_cookie_indices())
        self._tools_menu = QMenu("文件", self)
        _open_log_folder_action = QAction("显示日志文件", self)
        _open_log_folder_action.triggered.connect(self._open_log_folder)
        self._tools_menu.addAction(_open_log_folder_action)
        self.addMenu(self._tools_menu)

        self._setting_menu = QMenu("缓存设置", self)
        self.addMenu(self._setting_menu)

        delete_cookies_action = QAction("退出账号登录", self)
        delete_cookies_action.triggered.connect(self.delete_cookies)
        self._setting_menu.addAction(delete_cookies_action)

        delete_settings_action = QAction("清除OBS连接设置", self)
        delete_settings_action.triggered.connect(self._delete_settings)
        self._setting_menu.addAction(delete_settings_action)

        delete_app_settings = QAction("清除APP设置", self)
        delete_app_settings.triggered.connect(self._delete_app_settings)
        self._setting_menu.addAction(delete_app_settings)

        delete_bg = QAction("清除背景设置", self)
        delete_bg.triggered.connect(self._on_delete_bg)
        self._setting_menu.addAction(delete_bg)

        delete_cred = QAction("清空所有凭据", self)
        delete_cred.triggered.connect(self._delete_cred)
        self._setting_menu.addAction(delete_cred)

        self.account_menu = QMenu("账号切换", self)
        self.addMenu(self.account_menu)
        self.account_menu.aboutToShow.connect(self._populate_account_menu)
        self.account_group = QActionGroup(self,
                                          exclusionPolicy=QActionGroup.ExclusionPolicy.Exclusive)
        self.account_group.triggered.connect(self._switch_account)
        self._populate_account_menu()

    @Slot()
    def _populate_account_menu(self):
        self.account_menu.clear()
        for act in self.account_group.actions():
            self.account_group.removeAction(act)
            act.deleteLater()
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
        self.accountMenuPopulated.emit(self._cookie_index_len)

    @staticmethod
    @Slot()
    def _open_log_folder():
        log_dir, _ = get_log_path(is_makedir=False)
        QDesktopServices.openUrl(QUrl.fromLocalFile(log_dir))

    @Slot()
    def delete_cookies(self):
        self.logger.info(
            f"scanned={app_state.scan_status.scanned}, "
            f"expired={app_state.scan_status.expired}")
        if not app_state.scan_status["scanned"] and \
                not app_state.scan_status["expired"]:
            return
        expired = app_state.scan_status["expired"]
        cookie_index = CredentialManagerWorker.get_cookie_indices()
        self.logger.info(f"delete cookie index: {cookie_index}")
        with suppress(PasswordDeleteError):
            delete_password(KEYRING_SERVICE_NAME,
                            cookie_index[self._current_cookie_idx])
        cookie_index.remove(cookie_index[self._current_cookie_idx])
        self.logger.info(f"new cookie index: {cookie_index}")
        set_password(KEYRING_SERVICE_NAME, KEYRING_COOKIES_INDEX,
                     dumps(cookie_index))
        self._current_cookie_idx = max(0, self._current_cookie_idx - 1)
        self._populate_account_menu()
        CredentialManagerWorker.reset_default()
        self.cookieDeleted.emit(self._current_cookie_idx,
                                self._cookie_index_len == 0, expired)

    @Slot()
    def _delete_settings(self):
        with suppress(PasswordDeleteError):
            delete_password(KEYRING_SERVICE_NAME, KEYRING_SETTINGS)
        self.obsSettingsDeleted.emit()

    @Slot()
    def _delete_app_settings(self):
        with suppress(PasswordDeleteError):
            delete_password(KEYRING_SERVICE_NAME, KEYRING_APP_SETTINGS)
        app_state.app_settings_default()
        self.appSettingsDeleted.emit()

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
        if cache_base_dir(CacheType.CONFIG).is_dir():
            rmtree(cache_base_dir(CacheType.CONFIG))
        self.credDeleted.emit(True)

    @Slot()
    def _on_delete_bg(self):
        self.bgDeleted.emit()

    @Slot()
    def _switch_account(self, action: QAction):
        idx = action.data()
        self.logger.info(f"select account index: {idx}")
        if idx == self._cookie_index_len or not self._ready_switch_account():
            return
        elif idx != self._current_cookie_idx:
            self._current_cookie_idx = idx
            CredentialManagerWorker.reset_default()
            self.accountSwitch.emit(self._current_cookie_idx)

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

    def _add_new_account(self):
        if self._cookie_index_len == 0 or \
                self._current_cookie_idx == self._cookie_index_len:
            return
        self._current_cookie_idx = self._cookie_index_len
        CredentialManagerWorker.reset_default()
        self.accountAdded.emit(self._current_cookie_idx)
