from src.core.workers.base import Presenter


class AnnounceUpdatePresenter(Presenter):
    def __init__(self, view) -> None:
        super().__init__()
        self._view = view

    def prepare_fail_view(self):
        self._view.save_announce_btn.setEnabled(True)

    def prepare_success_view(self): ...

    def prepare_progress_view(self):
        pass
