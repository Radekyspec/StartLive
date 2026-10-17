"""Validated PK video configuration and preset selection helpers."""
from dataclasses import dataclass, field
from sys import platform

from startlive.core.constant.pk_encoder import (
    ENCODERS_BY_NAME,
    X264_PRESETS,
    NVENC_PRESETS,
    QUALITY_PRESETS,
    SCALE_MODES,
)


def aq_policy(encoder):
    return "optional" if encoder == "auto" else ENCODERS_BY_NAME[
        encoder].aq_policy


def platform_candidates(system=platform):
    if system.startswith("win"):
        names = ("av1_nvenc", "h264_nvenc", "av1_amf", "h264_amf",
                 "av1_qsv", "h264_qsv", "libsvtav1", "libx264")
    elif system == "darwin":
        names = ("h264_videotoolbox", "libsvtav1", "libx264")
    else:
        names = ("av1_nvenc", "h264_nvenc", "h264_vaapi", "av1_qsv",
                 "h264_qsv", "libsvtav1", "libx264")
    return tuple(ENCODERS_BY_NAME[name] for name in names)


def preset_choices(encoder):
    if encoder in ("libx264", "auto"):
        return X264_PRESETS
    if encoder in ("h264_nvenc", "av1_nvenc"):
        return NVENC_PRESETS
    return QUALITY_PRESETS


def translate_preset(encoder, value):
    """Keep quality intent when changing encoder or falling back to the CPU."""
    if value in preset_choices(encoder):
        return value
    if value in X264_PRESETS:
        value = ("performance" if value in X264_PRESETS[:3] else
                 "balanced" if value in X264_PRESETS[3:6] else "quality")
    elif value in NVENC_PRESETS:
        value = ("performance" if value in NVENC_PRESETS[:3] else
                 "balanced" if value == "p4" else "quality")
    if value not in QUALITY_PRESETS:
        raise ValueError("invalid PK encoder preset")
    if encoder in ("libx264", "auto"):
        return \
        {"performance": "veryfast", "balanced": "fast", "quality": "slow"}[
            value]
    if encoder in ("h264_nvenc", "av1_nvenc"):
        return {"performance": "p1", "balanced": "p4", "quality": "p7"}[value]
    return value


@dataclass(frozen=True, slots=True)
class VideoEncodingConfig:
    # Only these four fields are user preferences. The rest is application policy.
    encoder: str = "libx264"
    preset: str | None = None
    spatial_aq: bool = False
    scale_mode: str = "lanczos"

    bitrate_kbps: int = 5_000
    width: int = 1000
    height: int = 800
    frame_rate: int = 30
    rate_control: str = field(default="CBR", init=False)
    max_b_frames: int = field(default=0, init=False)
    keyframe_interval: int = field(default=2, init=False)
    min_bitrate_kbps: int = field(default=32, init=False)

    def __post_init__(self):
        if self.encoder != "auto" and self.encoder not in ENCODERS_BY_NAME:
            raise ValueError("unsupported video encoder")
        if self.preset is None:
            object.__setattr__(self, "preset",
                               translate_preset(self.encoder, "quality"))
        if self.preset not in preset_choices(self.encoder):
            raise ValueError(f"invalid preset for {self.encoder}")
        if type(self.spatial_aq) is not bool:
            raise ValueError("invalid PK AQ flag")
        # Store only an effective setting: SVT CBR requires AQ; backends
        # without an exposed AQ control must not carry a stale enabled flag.
        policy = aq_policy(self.encoder)
        if policy != "optional":
            object.__setattr__(self, "spatial_aq", policy == "required")
        if self.scale_mode not in dict(SCALE_MODES):
            raise ValueError("invalid PK scale mode")
        # Internal codec probes may use a smaller workload; persisted settings
        # can never override these application-controlled values.
        if type(self.bitrate_kbps) is not int or self.bitrate_kbps < self.min_bitrate_kbps:
            raise ValueError("invalid PK bitrate")
        if type(self.frame_rate) is not int or self.frame_rate <= 0:
            raise ValueError("invalid PK frame rate")
        if not (type(self.width) is int and type(self.height) is int
                and 2 <= self.width <= 3840 and 2 <= self.height <= 2160
                and self.width % 2 == self.height % 2 == 0):
            raise ValueError("PK resolution must be even and within 3840x2160")

    @property
    def codec_family(self):
        return "h264" if self.encoder == "auto" else ENCODERS_BY_NAME[
            self.encoder].codec_family

    @property
    def bitrate_bps(self):
        return self.bitrate_kbps * 1000

    def bitrate_limit(self, limits=None):
        """Cap the requested rate by the actual negotiated codec capacity.

        The encoder uses a one-second VBV, so its rate must also fit MaxCPB.
        No separate historical 20 Mbps ceiling remains when levels are upgraded.
        """
        if limits is None:
            return self.bitrate_bps
        return min(self.bitrate_bps, limits.max_bitrate, limits.max_cpb)

    def preferences(self):
        return {"encoder": self.encoder, "preset": self.preset,
                "spatial_aq": self.spatial_aq, "scale_mode": self.scale_mode}

    @classmethod
    def from_preferences(cls, values):
        if not isinstance(values, dict) or set(values) - {
            "encoder", "preset", "spatial_aq", "scale_mode"}:
            raise ValueError("invalid PK video preferences")
        return cls(**values)
