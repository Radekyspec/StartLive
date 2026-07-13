from abc import ABC, abstractmethod


class Dispatcher(ABC):
    @abstractmethod
    def close(self) -> None:
        pass

    @abstractmethod
    def post(self, fn, /, *args, **kwargs) -> None:
        pass
