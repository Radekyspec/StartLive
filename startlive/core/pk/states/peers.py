from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class PkInteractionScope:
    biz_session_id: str = field(repr=False)
    rtc_channel_id: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class PkMediaPreference:
    audio_muted: bool
    video_muted: bool


@dataclass(frozen=True, slots=True)
class PkRemoteMember:
    uid: int
    preference: PkMediaPreference
    raw: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)


@dataclass(frozen=True, slots=True)
class RtcPublication:
    uid: int
    video: bool
    audio: bool


@dataclass(frozen=True, slots=True)
class RtcSubscription:
    uid: int
    video: bool
    audio: bool


@dataclass(frozen=True, slots=True)
class RtcStream:
    video: bool = False
    audio: bool = False
    audio_muted: bool = False
    video_muted: bool = False
    spatial_layers: int = 0
    temporal_layers: int = 0


@dataclass(frozen=True, slots=True)
class RtcUserState:
    uid: int
    role: int
    published: bool
    stream: RtcStream
    raw: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)


@dataclass(frozen=True, slots=True)
class RtcUserEvent:
    kind: str  # joined/published/unpublished/left/audio_muted/video_muted metadata.
    uid: int
    stream: RtcStream | None = None
    reason_raw: int | None = None
