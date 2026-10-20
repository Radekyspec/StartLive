"""Exact-wire HTTP transport for verified PK request builders.

Numeric mode/action values belong to the verified business flow, not this
transport. No retries: several GET endpoints also mutate server state.
"""
from contextlib import contextmanager
from time import time

from startlive.core import constant
from startlive.core.constant.pk_api import (
    PK_SUCCESS,
    PK_CLASSIC_INFO_UNAVAILABLE,
    OPERATIONS,
)
from startlive.core.exceptions import PkError, PkProtocolError
from startlive.core.pk.pk_info import classic_info_result
from startlive.core.pk.states.session import PkIdentity, PkResult
from startlive.core.pk.trace import pk_trace
from startlive.core.sign.app_sign import (
    base_payload,
    encode_payload,
    livehime_sign,
    native_canonical,
    order_payload,
)
from startlive.core.workers.base.json_http import JsonHttpApi


class PkApi(JsonHttpApi):
    _http_label = "PK "
    _http_error = PkError
    _http_protocol_error = PkProtocolError

    def __init__(self, session, identity: PkIdentity, *, clock=time,
                 logger_name="PK"):
        self.session = session
        self.identity = identity
        self.clock = clock
        self.logger_name = logger_name
        # BaseWorker/create_session owns headers, captured cookies and proxy
        # behavior. This transport only constructs the protocol request.

    def request(self, operation: str, fields: dict[str, str], *,
                after_sign: dict[str, str] | None = None, parse_result=None,
                before_send=None):
        request_fields = dict(fields) | dict(after_sign or {})
        with self._preparing(operation, request_fields, before_send):
            method, path, form = self._prepare_request(operation, fields,
                                                       after_sign)
        return self._send(operation, method, path, form,
                          request_fields=request_fields,
                          parse_result=parse_result)

    def _prepare_request(self, operation, fields, after_sign):
        spec = OPERATIONS[operation]
        method, path = spec.method, spec.path
        common = base_payload()
        common.update(access_key=self.identity.access_key,
                      appkey=constant.APP_KEY,
                      ts=str(int(self.clock())))
        if (common.keys() | {"sign", "csrf", "csrf_token"}) & fields.keys():
            raise PkProtocolError("业务参数覆盖了身份或签名字段")
        extra = dict(after_sign or {})
        if extra.keys() - spec.post_sign_fields:
            raise PkProtocolError("该接口不支持指定的签后字段")
        if fields.keys() & spec.post_sign_fields:
            raise PkProtocolError("签后字段不能放入签名参数")
        for key, expected in (("room_id", self.identity.room_id),
                              ("ruid", self.identity.uid),
                              ("anchor_uid", self.identity.uid)):
            if key in fields and fields[key] != str(expected):
                raise PkProtocolError("PK 身份字段与当前账号不符")
        if operation in ("match", "cancel_match"):
            modern = {"biz_type", "connection_type"} & fields.keys()
            if modern and (modern != {"biz_type",
                                      "connection_type"} or "battle_type" in fields):
                raise PkProtocolError("PK 匹配类型分支必须互斥且完整")
        if spec.csrf:
            extra.update(csrf=self.identity.csrf, csrf_token=self.identity.csrf)
        if not spec.signed:
            form = native_canonical(common | fields | extra)
        else:
            signed = livehime_sign(common | fields, native_wire=True)
            signed.update(extra)  # CSRF and native trace fields are not signed.
            form = encode_payload(order_payload(signed), native_wire=True)
        return method, path, form

    def _context(self, operation, request_fields):
        spec = OPERATIONS.get(operation)
        method, path = (spec.method, spec.path) if spec else (None, None)
        # Invalid caller input can include reserved fields. Never log secrets
        # even when validation rejects the request before signing or sending.
        request = {key: value for key, value in request_fields.items()
                   if key.lower() not in {"access_key", "csrf", "csrf_token",
                                          "sign", "cookie",
                                          "authorization", "token",
                                          "access_token", "sessdata",
                                          "bili_jct"}}
        context = dict(operation=operation, method=method, path=path,
                       uid=self.identity.uid,
                       room_id=self.identity.room_id, request=request,
                       logger_name=self.logger_name)
        if request.get("client_traceid"):
            context["trace_id"] = request["client_traceid"]
        return context

    @contextmanager
    def _preparing(self, operation, fields, before_send):
        try:
            if before_send is not None:
                before_send()
            yield
        except Exception as error:
            pk_trace("http.error", **self._context(operation, fields),
                     stage="prepare",
                     response=None, http_status=None,
                     detail="请求尚未发送，无服务端响应",
                     error_type=type(error).__name__,
                     error=str(error) if isinstance(error,
                                                    PkError) else "请求准备失败")
            raise

    def _http_context(self, operation, method, path, fields):
        return self._context(operation, fields)

    @staticmethod
    def _http_trace(event, **fields):
        pk_trace(event, **fields)

    @staticmethod
    def _parsed_log_value(parsed):
        return parsed.data if isinstance(parsed, PkResult) else repr(parsed)

    @staticmethod
    def _http_failure_fields(error, response, stage, elapsed, *, network):
        fields = dict(stage=stage, elapsed_ms=elapsed)
        if network:
            fields.update(error="network_request_failed",
                          detail="网络请求失败，未取得可用响应" if response is None else "请求过程异常，响应已记录")
        else:
            fields["error"] = str(error) if isinstance(error,
                                                       PkError) else "响应处理失败"
        return fields

    @staticmethod
    def _parse_response(operation, result):
        # Native precheck accepts numeric-text codes. Preserve the project's
        # stop-on-error policy instead of the native controller's fall-through.
        if operation == "precheck" and isinstance(result, dict) and isinstance(
                result.get("code"), str):
            try:
                result["code"] = int(result["code"])
            except ValueError:
                pass
        if not isinstance(result, dict) or type(result.get("code")) is not int:
            raise PkProtocolError("PK 响应缺少有效的 code 字段")
        if operation == "classic_info" and result["code"] in (PK_SUCCESS,
                                                              PK_CLASSIC_INFO_UNAVAILABLE):
            # Contract44: only this callback consumes6204 and auto_match_status.
            # Preserve its code; it must not become generic request success.
            return PkResult(operation, classic_info_result(result["code"],
                                                           result.get("data")))
        if result["code"] != PK_SUCCESS:
            message = result.get("message")
            message = message.strip() if isinstance(message, str) else ""
            if operation == "update_user_settings" and message:
                raise PkError(message)
            reason = f"PK 服务拒绝请求（错误码 {result['code']}）"
            if message:
                reason += f"：{message}"
            raise PkError(reason)
        return PkResult(operation, result.get("data"))

    @staticmethod
    def _response_fields(response, parsed):
        fields = {"http_status": getattr(response, "status_code", None),
                  "response": parsed}
        try:
            body = getattr(response, "text", None)
            if isinstance(body, str):
                fields["response"] = body
        except Exception:
            # A custom response object must not turn diagnostics into failure.
            fields["response_log_error"] = "无法读取响应正文"
        return fields
