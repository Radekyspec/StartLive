from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class PkCandidate:
    uid: int
    uname: str = field(repr=False)
    face: str = field(repr=False)
    label: str = field(repr=False)
    label_type: str = field(repr=False)
    biz_session_id: str = field(repr=False)
    raw: dict[str, Any] = field(repr=False, compare=False)


@dataclass(frozen=True, slots=True)
class PkCandidatePage:
    users: tuple[PkCandidate, ...]
    page: int
    search_type: int
    has_next: bool
    raw: dict[str, Any] = field(repr=False, compare=False)
