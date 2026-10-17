from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class StoredCredential:
    key: str
    index: int


@dataclass(slots=True, frozen=True)
class RemovedCredential:
    key: str
    uid: str
    former_index: int
    remaining_keys: tuple[str, ...]
