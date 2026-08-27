from json import dumps

from src.core.constant import KEYRING_SERVICE_NAME


class FakeKeyring:
    def __init__(self):
        self.values: dict[tuple[str, str], str] = {}
        self.calls: list[tuple[str, str]] = []
        self.failures: dict[tuple[str, str], Exception] = {}

    def get_password(self, service: str, key: str) -> str | None:
        self.calls.append(("get", key))
        return self.values.get((service, key))

    def set_password(self, service: str, key: str, value: str) -> None:
        self.calls.append(("set", key))
        if error := self.failures.pop(("set", key), None):
            raise error
        self.values[(service, key)] = value

    def delete_password(self, service: str, key: str) -> None:
        self.calls.append(("delete", key))
        if error := self.failures.pop(("delete", key), None):
            raise error
        self.values.pop((service, key), None)

    def put(self, key: str, value: object) -> None:
        self.values[(KEYRING_SERVICE_NAME, key)] = dumps(value)
