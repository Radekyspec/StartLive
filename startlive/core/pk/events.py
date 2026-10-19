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
    PkInvitationContext,
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
    if not isinstance(data, dict):
        return None
    message = data.get("interact_join_message")
    if not isinstance(message, dict):
        return None
    config = message.get("config")
    if not isinstance(config, dict) or not isinstance(config.get("join_token"),
                                                      str) or not config[
        "join_token"]:
        return None
    # The common parser enforces config/biz_extra/stream_control and retains
    # the complete message. Never label a bare Handle success RTC-connected.
    return parse_pk_event("UNIVERSAL_INTERACT_JOIN", {"data": message})


def invitation_context_from_event(
        event: PkInvitationEvent) -> PkInvitationContext:
    if event.source is None:
        raise PkProtocolError("邀请缺少来源信息")
    # Native stores numeric64 then passes low32 to Handle. Confirmed sources
    # are positive small enums; retain signed32 interpretation for the DTO.
    source = event.source & 0xFFFFFFFF
    if source >= 1 << 31:
        source -= 1 << 32
    return PkInvitationContext(event.peer_search or 0, event.initiator or 0,
                               event.biz_session_id or "", source,
                               event.trace_id or "",
                               deepcopy(event.raw))


def _number(value):
    if type(value) is int:
        return value
    if isinstance(value, str) and value.isascii() and value.removeprefix(
            "-").isdecimal():
        return int(value)
    return None


def _text(value):
    return value if isinstance(value, str) else None


def _boolean(value):
    return value if type(value) is bool else None


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
        if isinstance(data.get("pk_basic"), dict):
            return PkInfoEvent(**common, info=parse_pk_info(data))
        return PkInfoHintEvent(**common, pk_id=_number(data.get("pk_id")),
                               pk_status=_number(data.get("pk_status")),
                               biz_session_id=_text(data.get("biz_session_id")))
    if command == "PK_BATTLE_MATCH_TIMEOUT":
        # Contract43 consumes only the int32 family, with an initialized zero
        # fallback. Do not borrow the round identity used by PRE/START/END.
        data = raw.get("data") if isinstance(raw.get("data"), dict) else {}
        battle_type = data.get("battle_type")
        if type(battle_type) is not int or not -(
                1 << 31) <= battle_type < 1 << 31:
            battle_type = 0
        return PkMatchTimeoutEvent(**common, battle_type=battle_type)
    if command in ("PK_BATTLE_PRE", "PK_BATTLE_START", "PK_BATTLE_END"):
        # Contract16: the round ID is rooted outside data. Native still reads
        # it when data is absent and retains initialized battle_type0.
        data = raw.get("data") if isinstance(raw.get("data"), dict) else {}
        fields = common | {"battle_type": _number(data.get("battle_type")) or 0,
                           "pk_id": _number(raw.get("pk_id"))}
        if command == "PK_BATTLE_PRE":
            return PkBattlePreEvent(**fields)
        if command == "PK_BATTLE_START":
            return PkBattleStartEvent(**fields, star_light_msg=_text(
                data.get("star_light_msg")),
                                      toast=_text(data.get("toast")))
        return PkBattleEndEvent(**fields)
    data = _object(raw, "data")
    session = {"biz_session_id": _text(data.get("biz_session_id")),
               "rtc_channel_id": _text(data.get("rtc_channel_id"))}
    if command == "UNIVERSAL_INTERACT_INVITATION":
        timeout = data.get("invitation_timeout")
        if type(timeout) is not int or not -(1 << 31) <= timeout < 1 << 31:
            timeout = None
        return PkInvitationEvent(**common, **session,
                                 uid=_number(data.get("uid")),
                                 peer_search=_number(data.get("peer_uid")),
                                 initiator=_number(data.get("initiator")),
                                 source=_number(data.get("source")),
                                 target_room_id=_number(
                                     data.get("target_room_id")),
                                 invitation_timeout=timeout,
                                 trace_id=_text(data.get("trace_id")),
                                 user_info=data.get("user_info") if isinstance(
                                     data.get("user_info"), dict) else {})
    if command == "UNIVERSAL_INTERACT_JOIN":
        config = _object(data, "config")
        extra, control = _object(data, "biz_extra"), _object(data,
                                                             "stream_control")
        return PkJoinEvent(**common,
                           biz_session_id=_text(config.get("biz_session_id")),
                           biz_label=_text(config.get("biz_label")),
                           rtc_channel_id=_text(config.get("rtc_channel_id")),
                           uid=_number(config.get("uid")),
                           join_token=_text(config.get("join_token")),
                           buvid=_text(config.get("buvid")),
                           enable_video=_boolean(
                               config.get("enable_video", False)),
                           enable_audio=_boolean(
                               config.get("enable_audio", False)),
                           reconnect=_boolean(data.get("reconnect")),
                           default_sub_mode=_number(
                               config.get("default_sub_mode")),
                           biz_extra=extra, stream_control=control)
    if command == "UNIVERSAL_INTERACT_OPERATION":
        return PkOperationEvent(**common, **session,
                                operation_type=_number(
                                    data.get("operation_type")),
                                action_type=_number(data.get("action_type")),
                                operator_uid=_number(data.get("operator_uid")),
                                target_uid=_number(data.get("target_uid")),
                                peer_search=_number(data.get("peer_uid")),
                                own_side=_boolean(data.get("own_side")),
                                source=_number(data.get("source")),
                                uid=_number(data.get("uid")),
                                initiator=_number(data.get("initiator")),
                                biz_label=_text(data.get("biz_label")),
                                invitation_timeout=_number(
                                    data.get("invitation_timeout")),
                                user_info=data.get("user_info") if isinstance(
                                    data.get("user_info"), dict) else {})
    if command == "UNIVERSAL_INTERACT_STREAM_CONTROL":
        config = _object(data, "config")
        return PkStreamControlEvent(
            **common, biz_session_id=_text(config.get("biz_session_id")),
            rtc_channel_id=_text(config.get("rtc_channel_id")),
            uid=_number(config.get("uid")),
            # 115's inner wire shape is not yet captured. Preserve unknown
            # values for diagnostics instead of failing event dispatch.
            stream_control=data.get("stream_control"))
    if command == "UNIVERSAL_INTERACT_LEAVE":
        return PkLeaveEvent(**common, **session, uid=_number(data.get("uid")),
                            close_user_reason=_number(
                                data.get("close_user_reason")),
                            toast=_text(data.get("toast")),
                            biz_label=_text(data.get("biz_label")))
