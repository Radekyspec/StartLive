"""Parsed RTC media sections; SDP may contain transport credentials."""
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class RtcSdpMedia:
    text: str = field(repr=False)
    mid: str
    kind: str
    direction: str
