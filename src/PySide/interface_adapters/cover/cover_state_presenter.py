from src.core.workers.base import Presenter


class CoverStateUpdatePresenter(Presenter):
    def __init__(self, view: "StreamConfigPanel"):
        super().__init__()
        self._view = view

    def prepare_success_view(self):
        self._view.cover_audit_state()

    def prepare_fail_view(self, exception: Exception): ...

    def prepare_progress_view(self, *args, **kwargs): ...
