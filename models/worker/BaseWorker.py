from typing import Optional

from PySide6.QtCore import QRunnable


class BaseWorker(QRunnable):
    name: str
    finished: bool
    exception: Optional[Exception]

    def __init__(self, name: str):
        super().__init__()
        self.name = name
        self.finished = False
        self.exception = None
