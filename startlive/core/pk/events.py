"""Decode known cmd/data projections after the push transport authenticates.

This is not a websocket handshake or a PK state machine. In particular a battle
end event does not imply that the business connection or RTC has ended.
"""
from copy import deepcopy

from startlive.core.constant.pk_events import EVENT_TYPES
from startlive.core.exceptions import PkProtocolError
from startlive.core.pk.states.events import (
    PkBattleEndEvent,
    PkBattlePreEvent,
    PkBattleStartEvent,
    PkInfoEvent,
    PkInfoHintEvent,
    PkInvitationEvent,
    PkJoinEvent,
    PkLeaveEvent,
    PkMatchTimeoutEvent,
    PkOperationEvent,
    PkStreamControlEvent,
)
from .pk_info import parse_pk_info


def accepts_join_buvid(event_buvid: str, *, local_buvid: str,
                       cookie_buvid3: str) -> bool:
    """Combined JOIN caller / CheckBuvidRight filter verified by native probes."""
    return (not event_buvid or not local_buvid or not cookie_buvid3
            or event_buvid == local_buvid or event_buvid == cookie_buvid3)


def join_from_handle_response(data):
    """Called only after the HTTP layer has validated application code0."""
    if data is None:
        return None
    message = data.get("interact_join_message")
    if message is None:
        return None
    config = _object(message, "config")
    if not _text(config, "join_token"):
        return None
    # The common parser enforces config/biz_extra/stream_control and retains
    # the complete message. Never label a bare Handle success RTC-connected.
    return parse_pk_event("UNIVERSAL_INTERACT_JOIN", {"data": message})


def _number(data, key):
    value = data.get(key)
    if value is None or type(value) is int:
        return value
    # Push IDs are supplied both as JSON integers and decimal strings.
    if isinstance(value, str) and value.isascii() and value.removeprefix(
            "-").isdecimal():
        return int(value)
    raise PkProtocolError(f"PK 事件 {key} 必须为整数或数字字符串：{value!r}")


def _text(data, key):
    value = data.get(key)
    if value is not None and not isinstance(value, str):
        raise PkProtocolError(f"PK 事件 {key} 必须为文本，实际为 {type(value).__name__}")
    return value


def _boolean(data, key, default=None):
    value = data.get(key, default)
    if value is not None and type(value) is not bool:
        raise PkProtocolError(f"PK 事件 {key} 必须为布尔值：{value!r}")
    return value


def _object(parent, key):
    value = parent.get(key)
    if not isinstance(value, dict):
        raise PkProtocolError(f"PK 事件缺少 {key} 对象")
    return value


def parse_pk_event(command, payload):
    if command not in EVENT_TYPES:
        return None
    if not isinstance(payload, dict):
        raise PkProtocolError("PK 事件内容无效")
    raw = deepcopy(payload)
    common = {"command": command, "raw": raw}
    if command == "PK_INFO":
        data = _object(raw, "data")
        if "pk_basic" in data:
            return PkInfoEvent(**common, info=parse_pk_info(data))
        return PkInfoHintEvent(**common, pk_id=_number(data, "pk_id"),
                               pk_status=_number(data, "pk_status"),
                               biz_session_id=_text(data, "biz_session_id"))
    if command == "PK_BATTLE_MATCH_TIMEOUT":
        # Contract43 defaults an absent family to zero, not malformed values.
        data = raw.get("data", {})
        battle_type = data.get("battle_type", 0)
        if type(battle_type) is not int or not -(1 << 31) <= battle_type < 1 << 31:
            raise PkProtocolError(f"PK 超时事件 battle_type 必须为 int32：{battle_type!r}")
        return PkMatchTimeoutEvent(**common, battle_type=battle_type)
    if command in ("PK_BATTLE_PRE", "PK_BATTLE_START", "PK_BATTLE_END"):
        # Contract16: the round ID is rooted outside data. Native still reads
        # it when data is absent and retains initialized battle_type0.
        data = raw.get("data", {})
        fields = common | {"battle_type": _number(data, "battle_type") or 0,
                           "pk_id": _number(raw, "pk_id")}
        if command == "PK_BATTLE_PRE":
            return PkBattlePreEvent(**fields)
        if command == "PK_BATTLE_START":
            return PkBattleStartEvent(**fields, star_light_msg=_text(data, "star_light_msg"),
                                      toast=_text(data, "toast"))
        return PkBattleEndEvent(**fields)
    data = _object(raw, "data")
    session = {"biz_session_id": _text(data, "biz_session_id"),
               "rtc_channel_id": _text(data, "rtc_channel_id")}
    if command == "UNIVERSAL_INTERACT_INVITATION":
        timeout = data.get("invitation_timeout")
        if timeout is not None and (
                type(timeout) is not int or not -(1 << 31) <= timeout < 1 << 31):
            raise PkProtocolError(f"PK 邀请 invitation_timeout 必须为 int32：{timeout!r}")
        return PkInvitationEvent(**common, **session,
                                 uid=_number(data, "uid"),
                                 peer_search=_number(data, "peer_uid"),
                                 initiator=_number(data, "initiator"),
                                 source=_number(data, "source"),
                                 target_room_id=_number(data, "target_room_id"),
                                 invitation_timeout=timeout,
                                 trace_id=_text(data, "trace_id"),
                                 user_info=_object(data, "user_info") if "user_info" in data else {})
    if command == "UNIVERSAL_INTERACT_JOIN":
        config = _object(data, "config")
        extra, control = _object(data, "biz_extra"), _object(data,
                                                             "stream_control")
        return PkJoinEvent(**common,
                           biz_session_id=_text(config, "biz_session_id"),
                           biz_label=_text(config, "biz_label"),
                           rtc_channel_id=_text(config, "rtc_channel_id"),
                           uid=_number(config, "uid"),
                           join_token=_text(config, "join_token"),
                           buvid=_text(config, "buvid"),
                           enable_video=_boolean(config, "enable_video", False),
                           enable_audio=_boolean(config, "enable_audio", False),
                           reconnect=_boolean(data, "reconnect"),
                           default_sub_mode=_number(config, "default_sub_mode"),
                           biz_extra=extra, stream_control=control)
    if command == "UNIVERSAL_INTERACT_OPERATION":
        return PkOperationEvent(**common, **session,
                                operation_type=_number(data, "operation_type"),
                                action_type=_number(data, "action_type"),
                                operator_uid=_number(data, "operator_uid"),
                                target_uid=_number(data, "target_uid"),
                                peer_search=_number(data, "peer_uid"),
                                own_side=_boolean(data, "own_side"),
                                source=_number(data, "source"),
                                uid=_number(data, "uid"),
                                initiator=_number(data, "initiator"),
                                biz_label=_text(data, "biz_label"),
                                invitation_timeout=_number(data, "invitation_timeout"),
                                user_info=_object(data, "user_info") if "user_info" in data else {})
    if command == "UNIVERSAL_INTERACT_STREAM_CONTROL":
        # Captured 115 carries identity directly in data.
        return PkStreamControlEvent(
            **common, biz_session_id=_text(data, "biz_session_id"),
            rtc_channel_id=_text(data, "rtc_channel_id"),
            uid=_number(data, "uid"),
            stream_control=_object(data, "stream_control"))
    if command == "UNIVERSAL_INTERACT_LEAVE":
        return PkLeaveEvent(**common, **session, uid=_number(data, "uid"),
                            close_user_reason=_number(data, "close_user_reason"),
                            toast=_text(data, "toast"),
                            biz_label=_text(data, "biz_label"))
