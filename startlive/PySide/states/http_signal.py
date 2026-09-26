from PySide6.QtCore import QObject, Signal


class HttpSignalEmitter(QObject):
    startLive = Signal()
    stopLive = Signal()
    exception = Signal(object)  # Signal(Exception)
