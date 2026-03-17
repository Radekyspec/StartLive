from PySide6.QtCore import Signal, QObject


class LoginState(QObject):
    areaUpdated = Signal()
    constUpdated = Signal()
    credentialLoaded = Signal()
    roomUpdated = Signal()
    qrExpired = Signal()
    qrNotConfirmed = Signal()
    qrScanned = Signal()
    versionChecked = Signal(str)
