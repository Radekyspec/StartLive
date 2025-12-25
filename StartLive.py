# -*- coding: utf-8 -*-
# module import
import sys
from argparse import ArgumentParser
from pathlib import Path
from platform import system
from subprocess import Popen

# package import
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import QApplication
from qdarktheme import enable_hi_dpi

# local package import
import app_state
from constant import *
from models.window import MainWindow

# Entry point
if __name__ == '__main__':
    if MainWindow.is_another_instance_running():
        sys.exit(0)
    if system() == "Windows":
        font_size = 9
        icon_file = "icon_left.ico"
        try:
            install_path = Path(__compiled__.containing_dir).resolve()
            updater_path = install_path / "Update.exe"
            app_path = install_path / f"app-{VERSION}"
            if updater_path.exists() and app_path.is_dir():
                Popen([updater_path, "--update=https://startlive.bydfk.com/"])
        except NameError:
            pass
    else:
        font_size = 12
        icon_file = "icon_left_macOS.ico"
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
    base_path = Path(__file__).resolve().parent
    app.setWindowIcon(
        QIcon(str(base_path / "resources" / icon_file)))
    if (font := app_state.app_settings["custom_font"]) and (
            f := QFont()).fromString(font):
        app.setFont(f)
    else:
        app.setFont(QFont(
            "Open Sans,.AppleSystemUIFont,Helvetica,Arial,MS Shell Dlg,sans-serif",
            font_size))
    window = MainWindow(args.web_host, args.web_port, args.first_run,
                        args.no_update, base_path=base_path)
    window.apply_color_scheme(app.styleHints().colorScheme())
    app.styleHints().colorSchemeChanged.connect(window.apply_color_scheme)
    window.show()
    sys.exit(app.exec())
