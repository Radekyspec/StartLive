from logging import Handler

from models.states import LogState


class QSignalLogHandler(Handler):
    _state: LogState

    def __init__(self):
        super().__init__()
        self._state = LogState()
        self.recordUpdated = self._state.recordUpdated

    def emit(self, record):
        msg = self.format(record)
        self._state.recordUpdated.emit(msg)