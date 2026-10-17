"""Confirmed code-zero precheck response fields.

Unlike LiveHime's observed fall-through on errors, StartLive stops on HTTP,
parse or application errors in PkApi. An error is never treated as eligibility.
"""
from startlive.core.pk.states.precheck import PkPrecheckResult


def parse_precheck(data) -> PkPrecheckResult:
    data = data if isinstance(data, dict) else {}
    tips = data.get("tips")
    tips = tips if isinstance(tips, dict) else {}
    show_type = data.get("show_type", 0)
    if type(show_type) is not int:
        show_type = 0
    return PkPrecheckResult(show_type, *(
        tips[key] if isinstance(tips.get(key), str) else ""
        for key in ("title", "content", "confirm_content")
    ))
