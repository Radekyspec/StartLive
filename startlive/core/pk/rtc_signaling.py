"""RTC RPC over an already-open binary data channel.

Transport setup is deliberately a separate dependency: these messages must
not be sent as HTTP, UDP datagrams, or to a guessed signaling websocket.
"""
import asyncio
from collections import deque
from contextlib import contextmanager

from startlive.core.constant.pk_wire import MAX_MESSAGE
from startlive.core.exceptions import PkError, PkProtocolError
from startlive.core.pk.rtc_wire import decode, encode
from .trace import pk_trace, sdp_for_trace


class RtcSignaling:
    def __init__(self, channel, ticket, *, notification=None, timeout=10):
        self.channel = channel
        self.ticket = ticket
        self.notification = notification
        self.timeout = timeout
        self.loop = asyncio.get_running_loop()
        self.pending = {}
        self.next_id = 1
        self.joined = False
        self.closed = False
        self._notification_blocks = 0
        self._buffered_notifications = deque()
        channel.on("message", self.receive)
        channel.on("close", self.close)

    def _trace(self, event, **fields):
        pk_trace(event, uid=self.ticket.get("uid"),
                 channel_id=self.ticket.get("channel_id"), **fields)

    def receive(self, raw):
        if self.closed:
            return
        if not isinstance(raw, bytes) or len(raw) > MAX_MESSAGE:
            self._trace("rtc.rpc.invalid", raw_type=type(raw).__name__,
                        raw_hex=raw.hex() if isinstance(raw, bytes) else None,
                        raw_text=raw if isinstance(raw, str) else None,
                        size=len(raw) if isinstance(raw,
                                                    (bytes, str)) else None)
            self.close(PkProtocolError("RTC 信令不是有效的二进制消息"))
            return
        try:
            message = decode("ResponseMessage", raw)
        except PkProtocolError:
            self._trace("rtc.rpc.decode.failed", raw_hex=raw.hex(),
                        size=len(raw))
            self.close(PkProtocolError("RTC 信令解析失败"))
            return
        request_id = message.get("request_id", 0)
        self._trace(
            "rtc.rpc.response" if request_id > 0 else "rtc.rpc.notification",
            request_id=request_id, response=message, raw_hex=raw.hex(),
            kinds=[key for key in message if
                   key.endswith(("_resp", "_notify"))],
            pending=request_id in self.pending,
            notification_blocks=self._notification_blocks)
        if request_id > 0:
            # Native matching accepts positive odd request IDs only.
            future = self.pending.get(request_id) if request_id & 1 else None
            if future is not None and not future.done():
                future.set_result(message)
        elif self._notification_blocks:
            # Native blocking is nested; capacity is explicit StartLive policy.
            if len(self._buffered_notifications) >= 256:
                self.close(PkError("RTC 初始化消息积压过多"))
            else:
                self._buffered_notifications.append(message)
        else:
            self._dispatch_notification(message)

    @contextmanager
    def block_notifications(self):
        self._notification_blocks += 1
        try:
            yield
        finally:
            self._notification_blocks -= 1
            if not self._notification_blocks:
                while self._buffered_notifications and not self.closed:
                    self._dispatch_notification(
                        self._buffered_notifications.popleft())

    def _dispatch_notification(self, message):
        self._trace("rtc.rpc.notification.dispatch", response=message)
        if self.notification:
            try:
                self.notification(message)
            except Exception as error:
                self._trace("rtc.rpc.notification.failed", error=error,
                            response=message)
                self.close(PkProtocolError("RTC 通知处理失败"))

    async def request(self, kind, payload, expected, *, parse_result=None):
        context = dict(kind=kind, expected=expected,
                       request={
                           key: sdp_for_trace(value) if key == "sdp" else value
                           for key, value in payload.items() if key != "token"})
        if self.closed or self.channel.readyState != "open":
            self._trace("rtc.rpc.rejected", **context, closed=self.closed,
                        channel_state=self.channel.readyState, response=None)
            raise PkError("RTC 信令通道尚未连接")
        request_id = self.next_id
        self.next_id += 2
        context["request_id"] = request_id
        future = self.loop.create_future()
        self.pending[request_id] = future
        response = None
        try:
            message = encode("RequestMessage", {
                "request_id": request_id,
                "channel_id": self.ticket["channel_id"],
                "uid": self.ticket["uid"], kind: payload,
            })
            self.channel.send(message)
            response = await asyncio.wait_for(future, self.timeout)
            if response.get("code", 0) != 0:
                raise PkError(f"RTC 服务拒绝请求（错误码 {response['code']}）")
            if expected not in response:
                raise PkProtocolError("RTC 响应类型与请求不符")
            parsed = parse_result(response[expected]) if parse_result else \
                response[expected]
            self._trace("rtc.rpc.success", **context, result=response[expected])
            return parsed
        except asyncio.TimeoutError:
            self._trace("rtc.rpc.timeout", **context, timeout=self.timeout,
                        response=response)
            raise PkError("RTC 请求超时") from None
        except BaseException as error:
            self._trace("rtc.rpc.failed", **context, error=error,
                        response=response)
            raise
        finally:
            self.pending.pop(request_id, None)

    async def join(self):
        result = await self.request("join_req", {
            "user": {"uid": self.ticket["uid"], "role": 0,
                     "platform": "pc_link",
                     "sdk_version": "2.7.5.60", "codec_capability": {}},
            "field2_unknown": True, "token": self.ticket["token"],
        }, "join_resp")
        self.joined = True
        return result

    async def leave(self):
        """Contract15: present, empty field5 over the existing reliable RPC.

        Block new media requests while awaiting completion. Cleanup belongs
        to the connection owner even when this request fails.
        """
        self._require_joined()
        self.joined = False
        return await self.request("leave_req", {}, "leave_resp")

    async def refresh_members(self, callid):
        self._require_joined()
        return await self.request("members_req", {
            "channel_id": self.ticket["channel_id"], "uid": self.ticket["uid"],
            "callid": callid,
        }, "members_resp")

    async def mute(self, media, muted):
        """Wire-only RPC; the owner must enforce publication/local-gate order.

        Contract35: modern native audio/video SDK entry points discard the
        provider's int32 index. The method selects the local publication arm;
        no source index or target UID belongs in MuteReq. Envelope identity
        still comes from this connection's authenticated ticket.
        A network timeout or missing payload remains an error. The native
        null-pointer completion case does not prove a missing reply is success.
        """
        self._require_joined()
        if media not in ("audio", "video") or type(muted) is not bool:
            raise PkProtocolError("RTC 静音请求需指定音频或视频及布尔值")
        return await self.request("mute_req", {media + "_muted": muted},
                                  "user_mute_resp")

    async def publish(self, sdp, *, video=True, audio=True, spatial_layers=1,
                      temporal_layers=1):
        """Layer defaults describe StartLive's single-layer encoder profile.

        Contract30 confirms the native settings/output default is temporal2,
        with a separate integer setting override accepted in range0..2. This
        encoder supports temporal1; do not copy the native default or inject
        temporal_count into PK HTTP/JOIN. Disabled video advertises neither.
        """
        self._require_joined()
        if not isinstance(sdp, str) or not sdp.startswith("v=0"):
            raise PkProtocolError("RTC 发布缺少本地 SDP offer")
        return await self.request("pub_req", {
            "sdp": sdp,
            "stream": {"video": video, "audio": audio, "audio_muted": False,
                       "video_muted": False,
                       "spatial_layers": max(spatial_layers, 1) if video else 0,
                       "temporal_layers": temporal_layers if video else 0},
        }, "pub_resp", parse_result=lambda result: self._answer(result,
                                                                allow_empty=not video and not audio))

    async def subscribe(self, peer_search, sdp, *, video=True, audio=True):
        self._require_joined()
        self._require_peer(peer_search)
        if not isinstance(sdp, str) or not sdp.startswith("v=0"):
            raise PkProtocolError("RTC 订阅缺少本地 SDP offer")
        return await self.request("sub_req", {
            "sdp": sdp,
            "users": [{"uid": peer_search, "video": video, "audio": audio,
                       "field4_unknown": 0}], "field3_unknown": True,
        }, "sub_resp", parse_result=self._answer)

    async def activate_subscription(self, peer_search, *, video=True,
                                    audio=True):
        """Enable delivery after the owner has applied SubResp's SDP answer.

        Native a7a60 -> a83e0 -> RPC slot+0x38 (136490) sends this separate
        reliable request. SubReq prepares tracks; its success alone does not
        complete subscription. Leave layer preferences unset, matching the
        native builder's negative preferred-layer indices.
        """
        self._require_joined()
        self._require_peer(peer_search)
        if type(video) is not bool or type(audio) is not bool:
            raise PkProtocolError("RTC 订阅开关必须为布尔值")
        return await self.request("update_sub_req", {
            "uid": peer_search, "audio": audio, "video": video,
        }, "update_sub_resp")

    def _require_peer(self, peer_search):
        if type(peer_search) is not int or peer_search <= 0 or peer_search == \
                self.ticket["uid"]:
            raise PkProtocolError("RTC 对端 UID 无效")

    def _require_joined(self):
        if not self.joined or self.closed:
            raise PkError("RTC 尚未入会")

    @staticmethod
    def _answer(result, *, allow_empty=False):
        # Empty successful zero-track PubResp is a delta for the existing
        # remote model; proto3 omits its empty string field.
        sdp = result.get("sdp", "" if allow_empty else None)
        if not isinstance(sdp, str) or (not allow_empty and not sdp.strip()):
            raise PkProtocolError("RTC 响应缺少 SDP answer")
        return sdp

    def close(self, error=None):
        if not self.closed:
            self._trace("rtc.rpc.closed", error=error,
                        pending_ids=list(self.pending),
                        buffered_notifications=len(
                            self._buffered_notifications))
        self.closed = True
        self.joined = False
        self._buffered_notifications.clear()
        for future in self.pending.values():
            if not future.done():
                future.set_exception(error or PkError("RTC 信令通道已断开"))
