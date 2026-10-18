from .Presenter import Presenter


class CallbackPresenter(Presenter):
    """Callback adapter; WorkerManager owns dispatch and thread affinity."""

    def __init__(self, *, finished, failed, progress=None):
        self.finished, self.failed, self.progress = finished, failed, progress

    def prepare_success_view(self, *args, **kwargs):
        self.finished(*args, **kwargs)

    def prepare_fail_view(self, exception):
        self.failed(exception.real_exc)

    def prepare_progress_view(self, *args, **kwargs):
        if self.progress is not None:
            self.progress(*args, **kwargs)
