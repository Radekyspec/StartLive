from .BaseWorker import BaseWorker


class LongLiveWorker(BaseWorker):
    _is_running: bool

    def __init__(self, name: str):
        super().__init__(name)
        self._is_running = True

    def stop(self) -> None:
        self._is_running = False
