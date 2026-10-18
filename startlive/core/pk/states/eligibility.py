from dataclasses import dataclass

from startlive.core.constant.pk import NativeInteractionState, NativePkType
from startlive.core.constant.pk_info import NativePkState


@dataclass(frozen=True, slots=True)
class PkVideoEligibilityState:
    """Explicit StartLive equivalents, supplied by the owning output/session.

    None means unknown. OBS capture being available alone does not establish
    live_output_active or server authorization. The native exception flag is
    deliberately not exposed as a bypass.
    """
    output_ready: bool | None
    live_output_active: bool | None
    interaction_state: NativeInteractionState | None
    interaction_business: int | None
    pk_state: NativePkState | None
    pk_type: NativePkType | None


@dataclass(frozen=True, slots=True)
class PkStartEligibilityState:
    output_ready: bool | None
    live_output_active: bool | None
    voice_microphone_available: bool | None
    pk_state: NativePkState | None


@dataclass(frozen=True, slots=True)
class PkStartEligibility:
    allowed: bool | None
    reason: str = ""
