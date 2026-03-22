from abc import ABC, abstractmethod


class Presenter(ABC):
    @abstractmethod
    def prepare_fail_view(self, *args, **kwargs):
        pass

    @abstractmethod
    def prepare_success_view(self, *args, **kwargs):
        pass

    @abstractmethod
    def prepare_progress_view(self, *args, **kwargs):
        pass
