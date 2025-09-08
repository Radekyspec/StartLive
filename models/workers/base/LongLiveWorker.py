from .BaseWorker import BaseWorker


class LongLiveWorker(BaseWorker):
    is_running: bool

    def __init__(self, name: str, *, with_session: bool = True):
        super().__init__(name, with_session=with_session)
        self.is_running = True

    def stop(self) -> None:
        self.is_running = False
