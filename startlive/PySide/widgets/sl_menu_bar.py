from pathlib import Path
from platform import system
from shutil import rmtree

from PySide6.QtCore import QUrl, Signal
from PySide6.QtCore import Slot
from PySide6.QtGui import QAction
from PySide6.QtGui import QActionGroup, QDesktopServices
from PySide6.QtWidgets import QMenuBar, QMenu
from PySide6.QtWidgets import QMessageBox

from startlive.PySide.interface_adapters.pk.session_controller import \
    PkSessionController
from startlive.PySide.log import get_logger, get_log_path
from startlive.core import app_state
from startlive.core.cache import cache_base_dir, del_cache_user
from startlive.core.constant import *
from startlive.core.constant.settings import SettingsName
from startlive.core.credentials import CredentialStore
from startlive.core.exceptions import MissingPkPluginError
from startlive.core.obs.plugin_install import install_pk_plugin


class StartLiveMenuBar(QMenuBar):
    cookieDeleted = Signal(int, bool)
    obsSettingsDeleted = Signal()
    appSettingsDeleted = Signal()
    bgDeleted = Signal()
    credentialClearRequested = Signal()
    credDeleted = Signal(bool)
    accountSwitch = Signal(int)
    accountAdded = Signal()

    def __init__(self, /, parent=None, *, resources_path: Path):
        super().__init__(parent)
        self.logger = get_logger(self.__class__.__name__)
        self._store = CredentialStore()
        self._resources_path = resources_path
        self._files_menu = QMenu("文件", self)
        _open_log_folder_action = QAction("显示日志文件", self)
        _open_log_folder_action.triggered.connect(self._open_log_folder)
        _install_obs_plugin_action = QAction("安装 OBS PK 插件", self)
        _install_obs_plugin_action.triggered.connect(self._install_pk_plugin)
        self._files_menu.addAction(_open_log_folder_action)
        self._files_menu.addAction(_install_obs_plugin_action)
        self.addMenu(self._files_menu)

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

        self._pk_window = None
        self._conversion_dialog = None
        self._tools_menu = QMenu("特殊功能", self)
        conversion_action = QAction("配置转换", self)
        conversion_action.triggered.connect(self._open_config_conversion)
        self._tools_menu.addAction(conversion_action)
        self.addMenu(self._tools_menu)
        pk_action = QAction("PK 连线", self)
        pk_action.triggered.connect(self._open_pk_window)
        self._tools_menu.addAction(pk_action)

    @Slot()
    def _open_pk_window(self):
        from startlive.PySide.window.pk_window import PkWindow

        if self._pk_window is None or self._pk_window._shutdown:
            if self._pk_window is not None:
                self._pk_window.deleteLater()
            self._pk_window = PkWindow(self,
                                       session_factory=PkSessionController)
        self._pk_window.show()
        self._pk_window.raise_()
        self._pk_window.activateWindow()

    @Slot()
    def _open_config_conversion(self):
        from startlive.PySide.window.config_conversion_dialog import \
            ConfigConversionDialog

        if self._conversion_dialog is None:
            self._conversion_dialog = ConfigConversionDialog(self)
        self._conversion_dialog.show()
        self._conversion_dialog.raise_()
        self._conversion_dialog.activateWindow()

    def shutdown_pk_window(self):
        """Retire the separate PK worker pool before changing account or exiting."""
        window = self._pk_window
        if window is None:
            return
        window.shutdown()
        window.close()
        window.deleteLater()
        self._pk_window = None

    @Slot()
    def _populate_account_menu(self):
        self.account_menu.clear()
        for act in self.account_group.actions():
            self.account_group.removeAction(act)
            act.deleteLater()
        cookie_indices = app_state.cookie_indices
        self.logger.info(
            f"cookie index length: {app_state.cookie_state.cookie_index_len}. ")
        for idx, cookie_index in enumerate(cookie_indices):
            act = QAction(app_state.usernames.get(cookie_index, cookie_index),
                          self, checkable=True)
            act.setData(idx)
            self.account_group.addAction(act)
            self.account_menu.addAction(act)
            if idx == app_state.cookie_state.current_cookie_idx:
                act.setChecked(True)
        self.account_menu.addSeparator()
        add_new_account = QAction("添加新账号", self)
        add_new_account.triggered.connect(self._add_new_account)
        self.account_menu.addAction(add_new_account)

    @staticmethod
    @Slot()
    def _open_log_folder():
        log_dir, _ = get_log_path(is_makedir=False)
        QDesktopServices.openUrl(QUrl.fromLocalFile(log_dir))

    @Slot()
    def delete_cookies(self):
        self.shutdown_pk_window()
        current = app_state.cookie_state.current_cookie_idx
        expected_keys = tuple(app_state.cookie_indices)
        removed = self._store.remove_at(current, expected_keys)
        if removed is None:
            self.logger.warning(
                "Manual credential removal skipped after index reconciliation."
            )
            self._populate_account_menu()
            return

        try:
            del_cache_user(removed.uid)
        except OSError:
            self.logger.warning(
                "Credential title cache cleanup failed after committed removal."
            )
        remaining = list(removed.remaining_keys)
        target = (
            max(0, min(removed.former_index - 1, len(remaining) - 1))
            if remaining
            else 0
        )
        self._populate_account_menu()
        result = (target, not remaining)
        self.cookieDeleted.emit(*result)
        return result

    @Slot()
    def _delete_settings(self):
        app_state.delete_settings(SettingsName.OBS)
        self.obsSettingsDeleted.emit()

    @Slot()
    def _delete_app_settings(self):
        if self._pk_window is not None:
            self._pk_window.close_encoder_settings()
        app_state.delete_settings(SettingsName.APP)
        app_state.delete_settings(SettingsName.PK_ENCODER)
        self.appSettingsDeleted.emit()

    @Slot()
    def _delete_cred(self):
        self.shutdown_pk_window()
        self.credentialClearRequested.emit()
        self._store.clear_all()
        for name in (SettingsName.OBS, SettingsName.APP,
                     SettingsName.PK_ENCODER):
            app_state.delete_settings(name)
        app_state.pk_encoder_runtime.reset()
        if cache_base_dir(CacheType.CONFIG).is_dir():
            rmtree(cache_base_dir(CacheType.CONFIG))
        self.credDeleted.emit(True)

    @Slot()
    def _on_delete_bg(self):
        self.bgDeleted.emit()

    @Slot()
    def _switch_account(self, action: QAction):
        target = action.data()
        self.logger.info(f"select account index: {target}")
        if (
                target != app_state.cookie_state.current_cookie_idx
                and target != app_state.cookie_state.cookie_index_len
                and self._ready_switch_account()
        ):
            self.accountSwitch.emit(target)

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
        return app_state.cookie_state.is_exhausted() or all(
            [app_state.scan_status["scanned"],
             app_state.scan_status["area_updated"],
             app_state.scan_status["room_updated"],
             app_state.scan_status["const_updated"],
             app_state.scan_status["announce_updated"]
             ]) or (app_state.scan_status["cred_loaded"] and not
        app_state.scan_status["expired"] and not app_state.scan_status[
            "scanned"])

    def _add_new_account(self):
        if app_state.cookie_state.cookie_index_len == 0 or \
                app_state.cookie_state.is_exhausted():
            return
        self.accountAdded.emit()

    @Slot()
    def _install_pk_plugin(self):
        try:
            destination = install_pk_plugin(self._resources_path)
        except MissingPkPluginError:
            QMessageBox.warning(
                self.parent(), "安装 OBS PK 插件",
                "未能找到对应平台的 OBS PK 插件\n\n"
                "若使用 pip 或从源代码运行，请自行编译安装仓库目录下 plugins/obs-startlive-pk 插件")
        except PermissionError as error:
            hint = "请先关闭 OBS，并检查插件目录的写入权限。"
            if system() == "Windows":
                hint += "必要时请以管理员身份运行开播器后重试。"
            QMessageBox.critical(self.parent(), "安装 OBS PK 插件失败",
                                 f"无法写入 OBS 插件目录。{hint}\n\n{error}")
        except OSError as error:
            QMessageBox.critical(self.parent(), "安装 OBS PK 插件失败",
                                 f"复制 OBS PK 插件失败，请关闭 OBS 后重试。\n\n{error}")
        else:
            QMessageBox.information(
                self.parent(), "安装 OBS PK 插件",
                f"OBS PK 插件已安装到：\n{destination}\n\n"
                "请重启 OBS，然后在“工具”菜单中开启 StartLive PK 采集。")
