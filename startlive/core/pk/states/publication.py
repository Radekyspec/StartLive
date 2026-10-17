from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PkPublishChannels:
    video: bool
    audio: bool
