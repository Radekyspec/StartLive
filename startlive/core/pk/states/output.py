from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PkOutputReadiness:
    output_ready: bool | None
    live_output_active: bool | None
    voice_microphone_available: bool | None
    reason: str
    source: str = "OBS GetStreamStatus"
