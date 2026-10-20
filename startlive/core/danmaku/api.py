"""Room bootstrap and sequence ACK HTTP, executed only by workers."""
from time import time

from startlive.core import constant
from startlive.core.danmaku.states.models import DanmakuBootstrap, DanmakuResult
from startlive.core.exceptions import DanmakuError, DanmakuProtocolError
from startlive.core.workers.base.json_http import JsonHttpApi
from .sign import sequence_ack_form, bootstrap_query
from .trace import danmaku_trace, response_for_trace


class DanmakuApi(JsonHttpApi):
    _http_label = "弹幕"
    _http_error = DanmakuError
    _http_protocol_error = DanmakuProtocolError

    def __init__(self, session, identity, *, clock=time):
        self.session, self.identity, self.clock = session, identity, clock

    def acknowledge_push_sequences(self, sequences):
        body = sequence_ack_form(
            access_key=self.identity.access_key, csrf=self.identity.csrf,
            sequences=sequences, version=constant.LIVEHIME_VERSION,
            timestamp=int(self.clock()))
        return self._send("push_sequence_ack", "POST",
                          "/xlive/open-interface/v1/dm/message_ack", body,
                          request_fields={"sequences": sequences})

    def fetch_push_bootstrap(self):
        query = bootstrap_query(access_key=self.identity.access_key,
                                room_id=self.identity.room_id, user_type=0,
                                is_anchor=True,
                                version=constant.LIVEHIME_VERSION,
                                timestamp=int(self.clock()))
        return self._send("push_bootstrap", "GET",
                          "/xlive/app-room/v1/index/getDanmuInfo", query,
                          request_fields={"room_id": self.identity.room_id},
                          parse_result=self._parse_bootstrap)

    @staticmethod
    def _parse_bootstrap(result):
        data = result.data
        if not isinstance(data, dict) or not isinstance(data.get("token"),
                                                        str) or not data[
            "token"]:
            raise DanmakuProtocolError("弹幕连接信息缺少令牌")
        endpoints = data.get("ip_list")
        if isinstance(endpoints, list):
            for endpoint in endpoints:
                if (isinstance(endpoint, dict) and isinstance(
                        endpoint.get("host"), str)
                        and endpoint["host"] and type(
                            endpoint.get("port")) is int
                        and 0 < endpoint["port"] <= 65535):
                    return DanmakuBootstrap(endpoint["host"], endpoint["port"],
                                            data["token"])
        return DanmakuBootstrap("broadcastlv.chat.bilibili.com", 2243,
                                data["token"])

    def _http_context(self, operation, method, path, fields):
        return dict(operation=operation, uid=self.identity.uid,
                    room_id=self.identity.room_id,
                    method=method, path=path, request=fields)

    @staticmethod
    def _http_trace(event, **fields):
        danmaku_trace(event, **fields)

    def _parsed_log_value(self, parsed):
        return self._safe_log_text(
            parsed.data if isinstance(parsed, DanmakuResult) else repr(parsed))

    @staticmethod
    def _http_failure_fields(error, response, stage, elapsed, *, network):
        if network:
            message = (
                "弹幕网络请求失败，未取得可用响应" if response is None else
                "弹幕请求过程异常，响应已记录")
        else:
            message = str(error) if isinstance(error,
                                               DanmakuError) else "弹幕响应处理失败"
        return {"error": message}

    @staticmethod
    def _parse_response(operation, result):
        if not isinstance(result, dict) or type(result.get("code")) is not int:
            raise DanmakuProtocolError("弹幕响应缺少有效的 code 字段")
        if result["code"] != 0:
            raise DanmakuError(f"弹幕服务拒绝请求（错误码 {result['code']}）")
        parsed = DanmakuResult(operation, result.get("data"))
        return parsed

    def _response_fields(self, response, parsed):
        fields = {"http_status": getattr(response, "status_code", None),
                  "response": None}
        try:
            body = getattr(response, "text", None)
            fields["response"] = self._safe_log_text(
                body if isinstance(body, str) else parsed)
        except Exception:
            fields["response_log_error"] = "无法读取响应正文"
        return fields

    def _safe_log_text(self, value):
        text = response_for_trace(value)
        for secret in (self.identity.access_key, self.identity.csrf,
                       *(value for _, value in self.identity.cookies)):
            if secret:
                text = text.replace(secret, "<redacted>")
        return text
