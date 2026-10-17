from pathlib import Path
from platform import system

from PySide6.QtCore import Slot
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMessageBox

from startlive.core.exceptions import MissingPkPluginError
from startlive.core.obs.plugin_install import install_pk_plugin


class InstallObsPkPluginAction(QAction):
    def __init__(self, parent=None, /, *, resources_path: Path):
        super().__init__("安装 OBS PK 插件", parent)
        self._resources_path = Path(resources_path)
        self.triggered.connect(self._install)

    @Slot()
    def _install(self):
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
