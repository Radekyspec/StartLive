from PySide6.QtCore import QObject, Signal


class RestartState(QObject):
    finished = Signal()
