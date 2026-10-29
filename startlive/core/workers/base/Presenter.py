from abc import ABC, abstractmethod


class Presenter(ABC):
    @abstractmethod
    def prepare_fail_view(self, exception: Exception):
        pass

    @abstractmethod
    def prepare_success_view(self, *args, **kwargs):
        pass

    def prepare_cancel_view(self):
        """Optional UI cleanup for a cancelled manager-owned worker."""

    @abstractmethod
    def prepare_progress_view(self, *args, **kwargs):
        pass
