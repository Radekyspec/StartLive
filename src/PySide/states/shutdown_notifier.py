from PySide6.QtCore import QObject, Signal


class ShutdownNotifier(QObject):
    finished = Signal()
