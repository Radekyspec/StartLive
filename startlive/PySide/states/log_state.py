from PySide6.QtCore import Signal, QObject


class LogState(QObject):
    recordUpdated = Signal(str)
