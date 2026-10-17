from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ObsOutputStatus:
    """Observed locally by the existing OBS request daemon, never from RTMP URL availability."""
    active: bool | None = None
    reconnecting: bool | None = None
    observed_at: float = 0.0
