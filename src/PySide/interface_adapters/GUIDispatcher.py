from PySide6.QtCore import QObject, Signal, Slot, Qt


class GUIDispatcher(QObject):
    _alive: bool
    _invoke = Signal(object)  # Signal(callable)

    def __init__(self) -> None:
        super().__init__()
        self._alive = True
        self._invoke.connect(
            self._run_in_gui,
            Qt.ConnectionType.QueuedConnection,
        )

    def close(self) -> None:
        self._alive = False

    def post(self, fn) -> None:
        if self._alive:
            self._invoke.emit(fn)

    @Slot(object)
    def _run_in_gui(self, fn) -> None:
        if self._alive:
            fn()
