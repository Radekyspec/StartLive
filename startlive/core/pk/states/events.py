from dataclasses import dataclass, field
from typing import Any

from startlive.core.pk.states.session import PkResult
from startlive.core.pk.states.info import PkInfo


@dataclass(frozen=True, slots=True)
class PkEvent:
    command: str
    raw: dict[str, Any] = field(repr=False)


@dataclass(frozen=True, slots=True)
class PkInfoEvent(PkEvent):
    info: PkInfo


@dataclass(frozen=True, slots=True)
class PkInvitationEvent(PkEvent):
    biz_session_id: str | None
    rtc_channel_id: str | None
    uid: int | None
    peer_search: int | None
    initiator: int | None
    source: int | None
    target_room_id: int | None
    invitation_timeout: int | None
    trace_id: str | None = field(repr=False)
    user_info: dict[str, Any] = field(repr=False)


@dataclass(frozen=True, slots=True)
class PkJoinEvent(PkEvent):
    biz_session_id: str | None
    biz_label: str | None
    rtc_channel_id: str | None
    uid: int | None
    join_token: str | None = field(repr=False)
    buvid: str | None = field(repr=False)
    enable_video: bool | None
    enable_audio: bool | None
    default_sub_mode: int | None
    reconnect: bool | None
    biz_extra: dict[str, Any] = field(repr=False)
    stream_control: dict[str, Any] = field(repr=False)


@dataclass(frozen=True, slots=True)
class PkOperationEvent(PkEvent):
    biz_session_id: str | None
    rtc_channel_id: str | None
    # Contract46/50: source5/7 cancel3; source7 sender refusal2/timeout4.
    # Each branch has its own UID key and applies only to a pending invitation.
    operation_type: int | None
    action_type: int | None
    operator_uid: int | None
    target_uid: int | None
    peer_search: int | None
    own_side: bool | None
    source: int | None = None


@dataclass(frozen=True, slots=True)
class PkLeaveEvent(PkEvent):
    biz_session_id: str | None
    rtc_channel_id: str | None
    uid: int | None
    close_user_reason: int | None
    toast: str | None = field(repr=False)


@dataclass(frozen=True, slots=True)
class PkRoundEvent(PkEvent):
    battle_type: int | None
    pk_id: int | None


@dataclass(frozen=True, slots=True)
class PkBattlePreEvent(PkRoundEvent):
    pass


@dataclass(frozen=True, slots=True)
class PkBattleStartEvent(PkRoundEvent):
    star_light_msg: str | None = field(repr=False)
    toast: str | None = field(repr=False)


@dataclass(frozen=True, slots=True)
class PkBattleEndEvent(PkRoundEvent):
    pass


@dataclass(frozen=True, slots=True)
class PkMatchTimeoutEvent(PkEvent):
    """Matching-family timeout; the native payload has no round/attempt ID."""
    battle_type: int = 0


@dataclass(frozen=True, slots=True)
class PkInvitationContext:
    """Verified dialog inputs; mapping from incoming events is still separate."""
    peer_search: int
    fallback_peer_uid: int
    biz_session_id: str = field(repr=False)
    source: int
    trace_id: str = field(repr=False)
    raw: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    @property
    def selected_peer_uid(self) -> int:
        """Preserve native invitation preference: positive peer UID first, else initiator."""
        return self.peer_search if self.peer_search > 0 else self.fallback_peer_uid


@dataclass(frozen=True, slots=True)
class PkInvitationEligibility:
    """None means the local eligibility decision has not been established."""
    allowed: bool | None
    reason: str = field(default="", repr=False)


@dataclass(frozen=True, slots=True)
class PkJoinEligibility:
    """Separate from invitation eligibility: JOIN has its own preceding gates."""
    allowed: bool | None
    reason: str = field(default="", repr=False)


@dataclass(frozen=True, slots=True)
class PkLocalQuit:
    reason: int
    toast: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class PkHandleResult:
    response: PkResult = field(repr=False)
    join_event: PkJoinEvent | None = field(repr=False)
