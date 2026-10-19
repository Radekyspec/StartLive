from dataclasses import dataclass, field
from typing import Any

from startlive.core.constant.pk_info import NativePkState, PkInfoAction


@dataclass(frozen=True, slots=True)
class PkBasicInfo:
    pk_id: int = 0
    init_id: int = 0
    status: int = 0
    type: int = 0
    sub_type: int = 0
    start_time: int = 0
    end_time: int = 0
    punish_end_time: int = 0
    sprint_duration: int = 0
    muti_pk_type: int = 0  # Response spelling; requests use mutipk_type.
    biz_session_id: str = field(default="", repr=False)
    punish_text: str = field(default="", repr=False)
    status_msg: str = field(default="", repr=False)


@dataclass(frozen=True, slots=True)
class PkMatchInfo:
    match_status: int = 0
    match_max_time: int = 0
    match_end_time: int = 0


@dataclass(frozen=True, slots=True)
class PkMemberInfo:
    uid: int = 0
    room_id: int = 0
    votes: int | None = None
    votes_text: str = field(default="", repr=False)
    uname: str = field(default="", repr=False)
    face: str = field(default="", repr=False)
    is_winner: int | None = None


@dataclass(frozen=True, slots=True)
class PkInfo:
    source_kind: int  # 3: HTTP query (classic or modern); 4: PK_INFO push.
    basic: PkBasicInfo
    match: PkMatchInfo
    timestamp: int
    raw: dict[str, Any] = field(repr=False, compare=False)
    legacy: bool = False  # Only classic conversion clears business context.
    members: tuple[PkMemberInfo, ...] = ()
    # Contracts48/49: explicit endpoint minus this snapshot's timestamp,
    # in seconds. None means unavailable, never an invented zero/end event.
    countdown_seconds: int | None = None


@dataclass(frozen=True, slots=True)
class PkClassicInfoResult:
    """Classic code6204 is a scoped reconciliation input, not HTTP success."""
    code: int
    auto_match_status: int
    data: dict[str, Any] = field(repr=False)


@dataclass(frozen=True, slots=True)
class PkInfoDecision:
    action: PkInfoAction
    info: PkInfo
    previous_state: NativePkState
    state: NativePkState
    reason: str = ""
