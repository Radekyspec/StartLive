from PySide6.QtCore import Signal, QObject


class StreamState(QObject):
    addressUpdated = Signal(str, str)
    faceRequired = Signal(str)
