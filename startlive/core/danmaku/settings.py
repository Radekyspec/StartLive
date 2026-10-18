"""Push context using StartLive's fixed, platform-independent client profile."""
from uuid import uuid4

from startlive.core import constant
from startlive.core.danmaku.states.models import DanmakuLoginSettings


def support_ack_setting(value, *, current=True) -> bool:
    # Native remote config reads a string; unreadable/missing keeps the setting.
    return value == "1" if isinstance(value, str) else current


def new_settings(*, buvid: str, device: str, osver: str,
                 support_ack: bool = True) -> DanmakuLoginSettings:
    return DanmakuLoginSettings(int(constant.LIVEHIME_BUILD), buvid,
                                constant.LIVEHIME_VERSION, device, osver,
                                support_ack, str(uuid4()))


def settings_for_identity(identity, *,
                          support_ack=True) -> DanmakuLoginSettings:
    # secret36983/3699e -> 36b7f reads environment+68 (cookie_buvid3).
    # HTTP buvid instead uses environment+50 (the application device ID).
    # Use this account snapshot; never substitute the HTTP device when absent.
    cookie_buvid = dict(identity.cookies).get("buvid3", "")
    return new_settings(buvid=cookie_buvid, device=constant.DEVICE_PLATFORM,
                        osver=constant.PK_PUSH_OSVER, support_ack=support_ack)
