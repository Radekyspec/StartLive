from dataclasses import dataclass, field
from typing import Any

from .peers import PkRemoteMember


@dataclass(frozen=True, slots=True)
class RtcBusinessMessage:
    uid: int
    message_type: int
    payload: bytes = field(repr=False)
    flag4_unknown: bool = False


@dataclass(frozen=True, slots=True)
class PkRoomInfo:
    interact_channel_id: str = field(repr=False)
    version: int
    members_version: int
    session_status: int
    room_status: int
    room_owner: int
    layout_id: str
    members: tuple[PkRemoteMember, ...]
    raw: dict[str, Any] = field(repr=False, compare=False)
