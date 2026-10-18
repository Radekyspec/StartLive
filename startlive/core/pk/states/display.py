from dataclasses import dataclass, field

from startlive.core.constant.pk_info import NativePkState


@dataclass(frozen=True, slots=True)
class PkRoundDisplay:
    """Confirmed round information, independent of transient RTC messages."""

    round_id: int | None
    state: NativePkState
    own_uid: int
    status_message: str = field(default="", repr=False)
    punish_text: str = field(default="", repr=False)
    peer_search: int | None = None
    peer_name: str = field(default="", repr=False)
    ended: bool = False
    own_name: str = field(default="", repr=False)
    own_votes: int | None = None
    own_votes_text: str = field(default="", repr=False)
    own_result: int | None = None
    peer_votes: int | None = None
    peer_votes_text: str = field(default="", repr=False)
    peer_result: int | None = None
    remaining_seconds: int | None = None
