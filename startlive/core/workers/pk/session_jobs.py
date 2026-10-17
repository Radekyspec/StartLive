from startlive.core.exceptions import PkError


class PkSessionJobs:
    """Track a flow's jobs without creating another thread pool or dispatcher."""

    def __init__(self, manager):
        self.manager = manager
        self.futures = []
        self.retired = False

    def submit(self, worker, **kwargs):
        if self.retired:
            raise PkError("PK 会话已关闭")
        self.futures = [future for future in self.futures if not future.done()]
        future = self.manager.submit(worker, **kwargs)
        self.futures.append(future)
        return future

    @property
    def busy(self):
        return any(not future.done() for future in self.futures)
