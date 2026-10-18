from PySide6.QtCore import QObject, Signal


class PKEncoderEvents(QObject):
    """Always deliver native worker callbacks to the GUI thread."""

    state_changed = Signal(str)
