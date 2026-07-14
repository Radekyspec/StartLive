# -*- coding: utf-8 -*-

import sys
from argparse import ArgumentParser, SUPPRESS
from pathlib import Path
from platform import system

from velopack import App

_velopack_first_run = False


def _on_velopack_first_run(_version) -> None:
    global _velopack_first_run
    _velopack_first_run = True


def main() -> int:
    # 必须在单实例检查、Qt 初始化和其他正常启动逻辑之前运行。
    # 安装、更新或卸载期间，Velopack 可能在这里直接终止进程。
    (
        App()
        .on_first_run(_on_velopack_first_run)
        .run()
    )

    # 将较重的应用模块放在 Velopack 启动处理之后导入，
    # 可以避免安装/更新钩子执行时初始化完整 UI。
    from PySide6.QtGui import QFont, QIcon
    from PySide6.QtWidgets import QApplication
    from qdarktheme import enable_hi_dpi

    from src.PySide.window import MainWindow
    from src.core import app_state

    if MainWindow.is_another_instance_running():
        return 0

    if system() == "Windows":
        font_size = 9
        icon_file = "icon_left.ico"
    else:
        font_size = 12
        icon_file = "icon_left_macOS.ico"

    parser = ArgumentParser()

    parser.add_argument(
        "--web.host",
        dest="web_host",
        default=None,
        help="Web服务绑定的主机地址",
    )
    parser.add_argument(
        "--web.port",
        dest="web_port",
        type=int,
        default=None,
        help="Web服务绑定的端口",
    )

    # 兼容旧 Squirrel 启动参数。
    parser.add_argument(
        "--squirrel-firstrun",
        dest="squirrel_first_run",
        action="store_true",
        help=SUPPRESS,
    )

    parser.add_argument(
        "--noupdate",
        dest="no_update",
        action="store_true",
    )

    args, qt_args = parser.parse_known_args()

    # Velopack 首次运行标志与旧 Squirrel 标志兼容
    first_run = _velopack_first_run or args.squirrel_first_run

    enable_hi_dpi()
    app = QApplication(qt_args)
    base_path = Path(__file__).resolve().parent
    app.setWindowIcon(
        QIcon(str(base_path / "resources" / icon_file))
    )

    if (
            (font := app_state.app_settings["custom_font"])
            and (custom_font := QFont()).fromString(font)
    ):
        app.setFont(custom_font)
    else:
        app.setFont(
            QFont(
                "Open Sans,.AppleSystemUIFont,Helvetica,"
                "Arial,MS Shell Dlg,sans-serif",
                font_size,
            )
        )

    window = MainWindow(
        args.web_host,
        args.web_port,
        first_run,
        args.no_update,
        base_path=base_path,
    )

    window.apply_color_scheme(
        app.styleHints().colorScheme()
    )
    app.styleHints().colorSchemeChanged.connect(
        window.apply_color_scheme
    )

    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
