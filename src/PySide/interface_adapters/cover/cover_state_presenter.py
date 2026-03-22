from src.core.workers.base import Presenter


class CoverStateUpdatePresenter(Presenter):
    def __init__(self, view):
        super().__init__()
        self._view = view

    def prepare_success_view(self, *args, **kwargs):
        self._view.cover_audit_state()

    def prepare_fail_view(self, *args, **kwargs): ...

    def prepare_progress_view(self, *args, **kwargs): ...
