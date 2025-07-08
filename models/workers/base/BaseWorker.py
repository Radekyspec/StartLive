from typing import Optional, Callable

from PySide6.QtCore import QRunnable, QObject, Signal


class BaseWorker(QRunnable):
    class Signals(QObject):
        finished = Signal()
        exception = Signal(Exception)

    name: str
    finished: bool
    exception: Optional[Exception]
    signals: Signals


    def __init__(self, name: str):
        super().__init__()
        self.name = name
        self.finished = False
        self.exception = None
        self.signals = self.Signals()

    @staticmethod
    def on_exception(*args, **kwargs):
        raise NotImplementedError

    @staticmethod
    def run_wrapper(func: Callable):

        def wrapped(self, *args, **kwargs):
            try:
                func(self, *args, **kwargs)
            except Exception as e:
                self.signals.exception.emit(e)
            finally:
                self.signals.finished.emit()

        return wrapped

    @staticmethod
    def on_finished(*args, **kwargs):
        raise NotImplementedError
