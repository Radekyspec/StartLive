from PySide6.QtCore import QObject, Signal


class ObsBtnState(QObject):
    obsConnecting = Signal()
    obsConnected = Signal()
    obsDisconnected = Signal()
