"""Precheck transport and validation; None permits the next request."""
from startlive.core.exceptions import PkProtocolError
from startlive.core.pk.parameters import precheck_fields
from .pk_request import PkRequestWorker


class PkPrecheckWorker(PkRequestWorker):
    operation = "precheck"

    def __init__(self, presenter, identity, /, kind, *, trace_id):
        super().__init__(presenter, identity,
                         fields=precheck_fields(identity, kind),
                         after_sign={"client_traceid": trace_id})

    def parse_result(self, data) -> str | None:
        # Run inside PkApi so malformed responses retain the complete HTTP log.
        if not isinstance(data, dict):
            raise PkProtocolError("PK 预检查响应缺少 data 对象")
        show_type = data.get("show_type", 0)
        if type(show_type) is not int:
            raise PkProtocolError(f"PK 预检查 show_type 必须为整数：{show_type!r}")
        tips = data.get("tips", {})
        if not isinstance(tips, dict):
            raise PkProtocolError("PK 预检查 tips 必须为对象")
        for key in ("title", "content", "confirm_content"):
            if key in tips and not isinstance(tips[key], str):
                raise PkProtocolError(f"PK 预检查 tips.{key} 必须为文本")
        if show_type == 1:
            return tips.get("content") or tips.get("title") or "当前无法开始 PK"
        return None
