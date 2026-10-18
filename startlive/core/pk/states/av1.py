from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Av1Limits:
    level: int
    max_pixels: int
    max_width: int
    max_height: int
    max_pixel_rate: int
    max_bitrate: int

    @property
    def max_cpb(self):
        # AV1 Annex A decoder buffer duration is one second.
        return self.max_bitrate

    @property
    def parameters(self):
        return {"profile": "0", "level-idx": str(self.level), "tier": "0"}
