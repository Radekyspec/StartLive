from .BaseWorker import BaseWorker


class LongLiveWorker(BaseWorker):
    is_running: bool

    def __init__(self, name: str):
        super().__init__(name)
        self.is_running = True

    def stop(self) -> None:
        self.is_running = False
