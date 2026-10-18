"""Local video-provider import check, before any PK business request."""
from importlib import import_module

from startlive.core.exceptions import PkError


def ensure_video_provider_ready():
    """Load the actual provider modules without creating a PC or any devices.

    Ordinary UDP has no exact-version restriction. Required-relay compatibility
    is checked separately only when the server ticket requires that transport.
    """
    try:
        for name in ("aiortc", "av", "startlive.core.pk.rtc_connection",
                     "startlive.core.pk.rtc_media"):
            import_module(name)
    except (ImportError, OSError):
        # Native-library loaders can raise either exception family. Keep local
        # loader paths and exception details out of the user-facing message.
        raise PkError(
            "视频 PK 音视频组件不可用，请安装或修复 StartLive 的 PK 组件") from None
