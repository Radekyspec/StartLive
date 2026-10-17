from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class VideoEncodingPlan:
    width: int
    height: int
    frame_rate: int
