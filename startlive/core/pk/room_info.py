"""Contract20 MessageNotify and UNIVERSAL_INFO_UPDATE_V2 room information.

StartLive binds this ingress to an explicitly established business context.
Native's traced type/command/version gate does not itself enforce that binding.
The caller owns this object per interaction and discards it at teardown; an
old connection must never be attached to a new context.
"""
import json
from collections import deque
from copy import deepcopy

from startlive.core.exceptions import PkProtocolError
from startlive.core.pk.states.room_info import (
    PkRoomInfo,
    PkRoomInfoBatch,
    PkRoomInfoContext,
    RtcBusinessMessage,
)
from .peers import room_info_members


def business_message(notification):
    """Project exact protobuf bytes; field4 has no inferred routing meaning."""
    value = notification.get("message_notify")
    if value is None:
        return None
    return RtcBusinessMessage(value.get("uid", 0), value.get("message_type", 0),
                              bytes.fromhex(
                                  value.get("payload", {}).get("hex", "")),
                              value.get("flag4_unknown", False))


def _number(data, key):
    value = data.get(key, 0)
    if type(value) is not int or not -(1 << 63) <= value < 1 << 63:
        raise PkProtocolError("连线房间信息的数值格式无效")
    return value


class PkRoomInfoIngress:
    def __init__(self, context, *, default_sub_mode, preferences=None):
        if not all((context.biz_session_id, context.business_label,
                    context.interact_channel_id)):
            raise PkProtocolError("尚未确认当前连线房间的业务身份")
        self.context = context
        self.default_sub_mode = default_sub_mode
        self.preferences = dict(preferences or {})
        self.version = 0

    def consume(self, message):
        if message.message_type != 0 and not 1001 <= message.message_type <= 1007:
            return None
        try:
            root = json.loads(message.payload)
        except (ValueError, UnicodeError):
            return None
        if not isinstance(root, dict) or root.get(
                "cmd") != "UNIVERSAL_INFO_UPDATE_V2":
            return None
        data = root.get("data")
        if not isinstance(data, dict):
            return None
        return self.consume_data(data)

    def consume_data(self, data):
        """Shared HTTP/RTC projection, after the caller checks the envelope."""
        context = PkRoomInfoContext(data.get("biz_session_id", ""),
                                    data.get("business_label", ""),
                                    data.get("interact_channel_id", ""))
        # Stricter StartLive policy, checked before updating the version. The
        # business interaction channel is deliberately not compared to RTC ID.
        if context != self.context:
            return None
        version = _number(data, "version")
        if version <= self.version:
            return None
        template = data.get("interact_template", {})
        if not isinstance(template, dict) or not isinstance(
                template.get("layout_id", ""), str):
            raise PkProtocolError("连线房间布局信息无效")
        result = PkRoomInfo(context, version, _number(data, "members_version"),
                            _number(data, "session_status"),
                            _number(data, "room_status"),
                            _number(data, "room_owner"),
                            template.get("layout_id", ""),
                            room_info_members(data,
                                              default_sub_mode=self.default_sub_mode,
                                              preferences=self.preferences),
                            deepcopy(data))
        # StartLive renders its own two panes, so this projection does not
        # fetch a native layout or claim its deferred callback timing. Member
        # removal/diff semantics are not inferred from members_version.
        self.version = version
        return result


class PkRoomInfoSession:
    """Pending JOIN -> correlated HTTP snapshot -> queued/current RTC V2.

    Exact session/label validation and bounded buffering are StartLive policy.
    Own RTC identity is retained separately from the HTTP business channel.
    Native poll timer/backoff and member removal semantics are not invented.
    """

    def __init__(self, join_event, *, preferences=None, queue_limit=256):
        if not join_event.biz_session_id or not join_event.biz_label or not join_event.rtc_channel_id:
            raise PkProtocolError("JOIN 缺少业务会话、标签或 RTC 频道")
        self.biz_session_id, self.biz_label = join_event.biz_session_id, join_event.biz_label
        self.rtc_channel_id = join_event.rtc_channel_id
        self.default_sub_mode = join_event.default_sub_mode
        self.preferences = dict(preferences or {})
        self.ingress = None
        self.stop_polling = self.closed = False
        self._pending = deque()
        self._queue_limit = queue_limit

    def receive_rtc(self, message):
        if self.closed:
            return None
        if self.ingress is None:
            if len(self._pending) >= self._queue_limit:
                raise PkProtocolError("确认房间身份前积压的 RTC 消息过多")
            self._pending.append(message)
            return None
        return self.ingress.consume(message)

    def accept_http(self, data):
        if self.closed:
            return PkRoomInfoBatch((), self.stop_polling)
        if not isinstance(data, dict):
            raise PkProtocolError("连线房间查询缺少 data 对象")
        context = PkRoomInfoContext(data.get("biz_session_id"),
                                    data.get("business_label"),
                                    data.get("interact_channel_id"))
        if (
                context.biz_session_id != self.biz_session_id or context.business_label != self.biz_label
                or not isinstance(context.interact_channel_id,
                                  str) or not context.interact_channel_id):
            raise PkProtocolError("连线房间查询与当前 JOIN 业务身份不符")
        if self.ingress is not None and context != self.ingress.context:
            raise PkProtocolError("业务房间频道发生变化，需要重新确认连线")
        ingress = self.ingress or PkRoomInfoIngress(context,
                                                    default_sub_mode=self.default_sub_mode,
                                                    preferences=self.preferences)
        # Contract20/22 HTTP same-session room_status2 stops only the poll loop,
        # before its version gate. It is not an instruction to stop RTC media.
        stopped = _number(data, "room_status") == 2
        snapshot = None if stopped else ingress.consume_data(data)
        self.ingress = ingress
        self.stop_polling = self.stop_polling or stopped
        infos = [snapshot] if snapshot is not None else []
        while self._pending:
            info = ingress.consume(self._pending.popleft())
            if info is not None:
                infos.append(info)
        return PkRoomInfoBatch(tuple(infos), self.stop_polling)

    def close(self):
        self.closed = True
        self._pending.clear()
