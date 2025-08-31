# -*- coding: utf-8 -*-

# module import
import sys
from argparse import ArgumentParser
from os.path import abspath, join, isdir, exists, dirname
from platform import system
from subprocess import Popen

# package import
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QApplication
                               )
from qdarktheme import enable_hi_dpi

# local package import
import config
from constant import *
from models.window import MainWindow

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
    if (font := config.app_settings["custom_font"]) and (
    f := QFont()).fromString(font):
        app.setFont(f)
    else:
        app.setFont(QFont(
            "Open Sans,.AppleSystemUIFont,Helvetica,Arial,MS Shell Dlg,sans-serif",
            9))
    window = MainWindow(args.web_host, args.web_port, args.first_run,
                        args.no_update, base_path=abspath(dirname(__file__)))
    window.apply_color_scheme(app.styleHints().colorScheme())
    app.styleHints().colorSchemeChanged.connect(window.apply_color_scheme)
    window.show()
    sys.exit(app.exec())
