"""Transport diagnostics never include credentials or room message bodies."""
from startlive.core.constant.danmaku_trace import _DESCRIPTIONS
import json
import re
from startlive.core.log import get_logger


def response_for_trace(value):
    """Retain response diagnostics without bootstrap/account tokens."""
    text = value if isinstance(value, str) else json.dumps(value,
                                                           ensure_ascii=False,
                                                           default=str)
    return re.sub(
        r'(?i)("(?:token|access_token|access_key|csrf|csrf_token|SESSDATA|bili_jct)"\s*:\s*")(?:\\.|[^"\\])*',
        r'\1<redacted>', text)


def danmaku_trace(event, **fields):
    try:
        get_logger("Danmaku").info(json.dumps(
            {"description": _DESCRIPTIONS.get(event, "弹幕推送处理记录"),
             "event": event, **fields}, ensure_ascii=False,
            separators=(",", ":"), default=str))
    except Exception:
        pass
