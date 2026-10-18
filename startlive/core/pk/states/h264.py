"""Negotiated H.264 limits for one PK publisher."""
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class H264Limits:
    level: int
    profile_level_id: str
    max_mbps: int
    max_fs: int
    max_dpb: int
    max_bitrate: int
    max_cpb: int
