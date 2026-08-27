import sys
import threading
import traceback

from PySide6.QtCore import QObject, Signal, Slot
from PySide6.QtWidgets import QMessageBox

from src.PySide.log import get_logger


class ErrorCenter(QObject):
    error_occurred = Signal(str)

    def __init__(self):
        super().__init__()
        self._showing_dialog = False
        self.error_occurred.connect(self.show_error_dialog)
        self._logger = get_logger(self.__class__.__name__)

    def report_exception(
            self,
            exc_type,
            exc_value,
            exc_traceback
    ):
        detail = "".join(
            traceback.format_exception(
                exc_type,
                exc_value,
                exc_traceback,
            )
        )

        # 无论弹窗是否成功，都先写入日志
        self._logger.critical(detail)

        # Signal 可以将后台线程中的异常安全地送回 GUI 线程
        self.error_occurred.emit(detail)

    @Slot(str)
    def show_error_dialog(self, detail):
        if self._showing_dialog:
            return

        self._showing_dialog = True

        try:
            box = QMessageBox()
            box.setIcon(QMessageBox.Icon.Critical)
            box.setWindowTitle("喜报")
            box.setText("StartLive开播器 出现未知错误")
            box.setInformativeText(
                "您可以点击下方按钮，了解错误发生的具体原因\n"
                "或前往「安装目录 / logs / StartLive.log」查看日志\n"
                "如果向他人寻求帮助，其你个发送生成的错误报告文件，而不是发送此窗口的截图，录屏"
                "视频，屏幕照片，拍摄的视频，手绘图片或誊抄的画面内容。"
            )
            box.setDetailedText(detail)
            box.setStandardButtons(QMessageBox.StandardButton.Ok)
            box.exec()
        except Exception:
            self._logger.exception("显示错误对话框时再次发生异常")
        finally:
            self._showing_dialog = False


def install_exception_handlers(error_center: ErrorCenter):
    original_hook = sys.excepthook

    # GUI 主线程以及普通未捕获异常
    def global_exception_hook(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            original_hook(exc_type, exc_value, exc_traceback)
            return

        error_center.report_exception(
            exc_type,
            exc_value,
            exc_traceback,
        )

    sys.excepthook = global_exception_hook

    # threading.Thread 中的异常
    def thread_exception_hook(args):
        error_center.report_exception(
            args.exc_type,
            args.exc_value,
            args.exc_traceback
        )

    threading.excepthook = thread_exception_hook

    # __del__ 等无法正常抛出的异常
    def unraisable_exception_hook(args):
        error_center.report_exception(
            type(args.exc_value),
            args.exc_value,
            args.exc_traceback
        )

    sys.unraisablehook = unraisable_exception_hook
