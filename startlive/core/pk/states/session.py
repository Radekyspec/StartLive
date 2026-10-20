from dataclasses import dataclass, field

from startlive.core.constant.pk import PkMode, NativePkType
from startlive.core.danmaku.states.models import DanmakuIdentity, DanmakuResult
from startlive.core.pk.states.candidates import PkCandidate

# Public aliases are assignments, not import re-exports, so an import
# optimizer cannot silently delete this module's external contract.
PkIdentity = DanmakuIdentity
PkResult = DanmakuResult


@dataclass(frozen=True, slots=True)
class PkContinuousStatus:
    status: int
    button_disabled: bool
    toast: str = field(repr=False)
    pk_versions: tuple[int, ...]
    effect_pk_version: int

    def enabled_for(self, kind: NativePkType) -> bool:
        # Query values 1 AND 2 mean enabled; update requests instead use bool 0/1.
        return self.status in (1, 2) and kind.server_type in self.pk_versions


@dataclass(frozen=True, slots=True)
class PkOptions:
    mode: PkMode
    peer_search: int | None = None  # None means random matching.
    continuous: bool = False
    candidate: PkCandidate | None = None


@dataclass(frozen=True, slots=True)
class RtcTicket:
    channel_id: int
    uid: int
    access_token: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class MediaPacket:
    kind: int  # 1 = video in pixel_format, 2 = interleaved stereo s16le
    timestamp_ns: int
    width: int = 0
    height: int = 0
    sample_rate: int = 0
    frames: int = 0
    payload: bytes | memoryview = field(default=b"", repr=False)
    pixel_format: str = "bgra"  # Remote decoded frames also use this model.
    colorspace: str = "ITU709"
    color_range: str = "JPEG"
