"""PK encoder policy and backend preset mappings."""
from startlive.core.pk.states.encoder_choice import EncoderChoice

X264_PRESETS = ("ultrafast", "superfast", "veryfast", "faster", "fast",
                "medium", "slow", "slower", "veryslow")

NVENC_PRESETS = tuple(f"p{i}" for i in range(1, 8))

QUALITY_PRESETS = ("performance", "balanced", "quality")

SCALE_MODES = (
    ("bilinear", "双线性（速度优先）"),
    ("bicubic", "双三次（均衡）"),
    ("lanczos", "Lanczos（清晰度优先）"),
    ("area", "区域平均（适合缩小）"),
    ("point", "最近邻（保留像素边缘）"),
)

# name, display label, codec family, spatial AQ policy
ENCODER_DEFINITIONS = (
    ('av1_nvenc', 'NVIDIA NVENC AV1', 'av1', 'optional'),
    ('h264_nvenc', 'NVIDIA NVENC H.264', 'h264', 'optional'),
    ('av1_amf', 'AMD AMF AV1', 'av1', 'optional'),
    ('h264_amf', 'AMD AMF H.264', 'h264', 'unavailable'),
    ('av1_qsv', 'Intel Quick Sync AV1', 'av1', 'unavailable'),
    ('h264_qsv', 'Intel Quick Sync H.264', 'h264', 'unavailable'),
    ('h264_videotoolbox', 'Apple VideoToolbox H.264', 'h264', 'unavailable'),
    ('h264_vaapi', 'VA-API H.264', 'h264', 'unavailable'),
    ('libx264', 'x264 (CPU)', 'h264', 'optional'),
    ('libsvtav1', 'SVT-AV1 (CPU)', 'av1', 'required'),
)

AMF_PRESETS = {"performance": "speed", "balanced": "balanced",
               "quality": "quality"}

QSV_PRESETS = {"performance": "veryfast", "balanced": "medium",
               "quality": "slow"}

# Quality-first within SVT's low-delay presets, not offline slow encoding.
SVT_PRESETS = {"performance": "12", "balanced": "10", "quality": "8"}

PROBE_TIMEOUT_SECONDS = 12.0

ENCODERS = tuple(EncoderChoice(*values) for values in ENCODER_DEFINITIONS)

ENCODERS_BY_NAME = {item.name: item for item in ENCODERS}
