from typing import Protocol


class Dispatcher(Protocol):
    def close(self) -> None:
        ...

    def post(self, fn, /, *args, **kwargs) -> None:
        ...
