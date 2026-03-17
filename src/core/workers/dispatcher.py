class Dispatcher:
    def close(self) -> None:
        raise NotImplementedError

    def post(self, fn) -> None:
        raise NotImplementedError
