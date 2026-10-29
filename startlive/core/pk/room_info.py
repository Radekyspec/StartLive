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
    RtcBusinessMessage,
)
from .peers import room_info_members
from .trace import pk_trace


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


def parse_stream_controls(value):
    """Parse known controls atomically; retain unknown extension names for logs.

    Malformed known fields raise before the owner advances any media version.
    """
    if not isinstance(value, dict):
        raise PkProtocolError(
            f"stream_control 必须为对象，实际为 {type(value).__name__}")
    parsed, issues = {}, []
    unknown = value.keys() - {"audio_control", "video_control", "pub_sub_control"}
    if unknown:
        issues.append(f"Unknown stream_control fields: {sorted(unknown)}")
    for media in ("audio", "video"):
        key = media + "_control"
        if key not in value:
            continue
        control = value[key]
        if not isinstance(control, dict):
            raise PkProtocolError(
                f"{key} 必须为对象，实际为 {type(control).__name__}")
        version = control.get("version")
        if type(version) is not int:
            raise PkProtocolError(f"{key}.version 必须为整数：{version!r}")
        fields = {"version": version}
        unknown = control.keys() - {"version", "operator_uid", "mute_local_mode", "mute_remote_uids"}
        if unknown:
            issues.append(f"Unknown {key} fields: {sorted(unknown)}")
        if not {"mute_local_mode", "mute_remote_uids"}.intersection(control):
            issues.append(f"{key} has no recognized mute fields")
        if "mute_local_mode" in control:
            mode = control["mute_local_mode"]
            if type(mode) is int and mode in (0, 1):
                fields["mute_local_mode"] = bool(mode)
            else:
                raise PkProtocolError(f"{key}.mute_local_mode 必须为 0 或 1：{mode!r}")
        if "mute_remote_uids" in control:
            remotes = control["mute_remote_uids"]
            if remotes is None:
                fields["mute_remote_uids"] = ()
            elif isinstance(remotes, list) and all(type(uid) is int for uid in remotes):
                fields["mute_remote_uids"] = tuple(remotes)
            else:
                raise PkProtocolError(
                    f"{key}.mute_remote_uids 必须为整数列表或 null：{remotes!r}")
        parsed[media] = fields
    return parsed, tuple(issues)


class PkRoomInfoSession:
    """Pending JOIN -> correlated HTTP snapshot -> queued/current RTC V2.

    Exact session/label validation and bounded buffering are StartLive policy.
    Own RTC identity is retained separately from the HTTP business channel.
    Native poll timer/backoff and member removal semantics are not invented.
    """

    def __init__(self, join_event):
        if not join_event.biz_session_id or not join_event.biz_label or not join_event.rtc_channel_id:
            raise PkProtocolError("JOIN 缺少业务会话、标签或 RTC 频道")
        self.biz_session_id, self.biz_label = join_event.biz_session_id, join_event.biz_label
        self.rtc_channel_id = join_event.rtc_channel_id
        self.default_sub_mode = join_event.default_sub_mode
        self.interact_channel_id = None
        self.version = 0
        self.stop_polling = self.closed = False
        self._pending = deque()

    def receive_rtc(self, message):
        if self.closed:
            return None
        if self.interact_channel_id is None:
            if len(self._pending) >= 256:
                raise PkProtocolError("确认房间身份前积压的 RTC 消息过多")
            self._pending.append(message)
            return None
        return self._consume(message)

    def accept_http(self, data):
        if self.closed:
            return ()
        if not isinstance(data, dict):
            raise PkProtocolError("连线房间查询缺少 data 对象")
        channel = data.get("interact_channel_id")
        if (data.get("biz_session_id") != self.biz_session_id
                or data.get("business_label") != self.biz_label
                or not isinstance(channel, str) or not channel):
            raise PkProtocolError("连线房间查询与当前 JOIN 业务身份不符")
        if self.interact_channel_id is not None and channel != self.interact_channel_id:
            raise PkProtocolError("业务房间频道发生变化，需要重新确认连线")
        # Contract20/22 HTTP same-session room_status2 stops only the poll loop,
        # before its version gate. It is not an instruction to stop RTC media.
        stopped = _number(data, "room_status") == 2
        snapshot = None if stopped else self._consume_data(data, channel)
        self.interact_channel_id = channel
        self.stop_polling = self.stop_polling or stopped
        infos = [snapshot] if snapshot is not None else []
        while self._pending:
            info = self._consume(self._pending.popleft())
            if info is not None:
                infos.append(info)
        return tuple(infos)

    def close(self):
        self.closed = True
        self._pending.clear()

    def _consume(self, message):
        if message.message_type != 0 and not 1001 <= message.message_type <= 1007:
            return None
        try:
            root = json.loads(message.payload)
        except (ValueError, UnicodeError) as error:
            pk_trace("room.info.decode.failed", uid=message.uid,
                     message_type=message.message_type, size=len(message.payload),
                     error_type=type(error).__name__, error=str(error))
            raise PkProtocolError(
                f"RTC 业务消息 JSON 解析失败：{type(error).__name__}: {error}") from error
        if not isinstance(root, dict):
            raise PkProtocolError(
                f"RTC 业务消息必须为对象，实际为 {type(root).__name__}")
        if root.get("cmd") != "UNIVERSAL_INFO_UPDATE_V2":
            return None
        data = root.get("data")
        if not isinstance(data, dict):
            raise PkProtocolError("UNIVERSAL_INFO_UPDATE_V2 缺少 data 对象")
        return self._consume_data(data, self.interact_channel_id)

    def _consume_data(self, data, channel):
        """Shared HTTP/RTC projection, after the caller checks the envelope."""
        # Check the fixed JOIN identity before advancing the version.
        # The business channel is deliberately not compared to the RTC ID.
        if (data.get("biz_session_id", "") != self.biz_session_id
                or data.get("business_label", "") != self.biz_label
                or data.get("interact_channel_id", "") != channel):
            return None
        version = _number(data, "version")
        if version <= self.version:
            return None
        template = data.get("interact_template", {})
        if not isinstance(template, dict) or not isinstance(
                template.get("layout_id", ""), str):
            raise PkProtocolError("连线房间布局信息无效")
        result = PkRoomInfo(channel, version, _number(data, "members_version"),
                            _number(data, "session_status"),
                            _number(data, "room_status"),
                            _number(data, "room_owner"),
                            template.get("layout_id", ""),
                            room_info_members(data,
                                              default_sub_mode=self.default_sub_mode),
                            deepcopy(data))
        # StartLive renders its own two panes, so this projection does not
        # fetch a native layout or claim its deferred callback timing. Member
        # removal/diff semantics are not inferred from members_version.
        self.version = version
        return result
