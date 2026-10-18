from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class EncoderChoice:
    name: str
    label: str
    codec_family: str = "h264"
    aq_policy: str = "unavailable"
