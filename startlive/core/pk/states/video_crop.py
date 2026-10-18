from dataclasses import dataclass
from math import gcd, isfinite

from startlive.core.constant.pk_video_config import DEFAULT_VIDEO_CONFIG


@dataclass(frozen=True, slots=True)
class VideoCrop:
    # Fraction of the available travel, so a source size change preserves framing.
    x: float = 0.5
    y: float = 0.5

    def __post_init__(self):
        if not all(isfinite(value) and 0 <= value <= 1 for value in
                   (self.x, self.y)):
            raise ValueError("invalid video crop position")

    def rectangle(self, width, height):
        """Return an in-bounds, even BGRA/I420 crop matching the fixed target."""
        target = DEFAULT_VIDEO_CONFIG
        divisor = gcd(target.width, target.height)
        unit_width, unit_height = 2 * target.width // divisor, 2 * target.height // divisor
        units = min(width // unit_width, height // unit_height)
        if units < 1:
            raise ValueError(
                f"source video must be at least {unit_width}x{unit_height}")
        crop_width, crop_height = units * unit_width, units * unit_height
        left = round((width - crop_width) * self.x / 2) * 2
        top = round((height - crop_height) * self.y / 2) * 2
        left = min(left, (width - crop_width) // 2 * 2)
        top = min(top, (height - crop_height) // 2 * 2)
        return left, top, crop_width, crop_height
