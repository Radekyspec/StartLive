"""Derive the output plan from a captured PK encoder configuration."""

from startlive.core.pk.states.video import VideoEncodingPlan


def configured_plan(source_width, source_height, limits, config):
    """Use the fixed output target, reducing it only for negotiated limitations."""
    from .rtc_h264 import encoding_plan
    if source_width < 2 or source_height < 2:
        raise ValueError("invalid source video size")
    if config.codec_family == "av1":
        from .rtc_av1 import encoding_plan as av1_plan
        return av1_plan(config, limits)
    base = encoding_plan(config.width, config.height, limits)
    return VideoEncodingPlan(base.width, base.height,
                             min(base.frame_rate, config.frame_rate))
