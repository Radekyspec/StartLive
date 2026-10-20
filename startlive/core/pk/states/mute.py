from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True, slots=True)
class RtcMuteState:
    requested: bool | None = None
    local_muted: bool = False
    acknowledged: bool | None = None
    pending: bool = False


@dataclass(frozen=True, slots=True)
class RtcMuteRequest:
    media: Literal["audio", "video"]
    muted: bool
    signal: bool = True
    request_id: int | None = None


@dataclass(frozen=True, slots=True)
class RtcMuteUpdate:
    media: Literal["audio", "video"]
    state: RtcMuteState
    error: str | None = None
    request_id: int | None = None
