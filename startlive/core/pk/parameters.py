"""Business parameters confirmed by native callers, separate from HTTP signing."""
from startlive.core.constant.pk import NativePkType
from startlive.core.exceptions import PkProtocolError
from startlive.core.pk.states.session import PkContinuousStatus


def precheck_fields(identity, kind: NativePkType):
    result = {"room_id": str(identity.room_id),
              "pk_version": str(kind.server_type),
              "mobi_app": "pc_link"}
    if kind == NativePkType.DOUBLE_CLASSIC:
        result["uid"] = str(identity.uid)
    return result


def match_fields(identity, kind: NativePkType):
    result = {"room_id": str(identity.room_id)}
    if kind is NativePkType.DOUBLE_RANDOM_CONNECT:
        result.update(biz_type="1", connection_type="1")
    else:
        result["battle_type"] = str(kind.server_type)
    return result


def continuous_fields(identity, kind: NativePkType, enabled: bool,
                      trace_id: str):
    if kind not in (NativePkType.DOUBLE_CLASSIC, NativePkType.CHATROOM_CLASSIC,
                    NativePkType.DOUBLE_RANDOM):
        raise PkProtocolError("该 PK 类型的连续开关尚未确认")
    return {"ruid": str(identity.uid), "status": "1" if enabled else "0",
            "pk_version": str(kind.server_type), "client_traceid": trace_id}


def video_invite_fields(peer_search: int, *, invited_type_label: str):
    """Directed video PK search: native5 -> precheck6 -> startMutiPK4.

    The chosen Search response row supplies data.users[].label_type. It is
    distinct from both the query category and the candidate's display label.
    """
    result = {"mutipk_type": "4", "invite_uid": f"{peer_search:d}",
              "invited_type": "1"}
    if invited_type_label:
        result["invited_type_label"] = invited_type_label
    return result


def connect_fields(peer_uid: int, *, invited_type_label: str):
    return {"business_label": "universal_multi_conn", "cancel_current": "0",
            "invited_type": "3", "invited_type_label": invited_type_label,
            "peer_uid": f"{peer_uid:d}"}


def cancel_connect_fields(peer_uid: int):
    result = cancel_video_invite_fields(peer_uid)
    return result | {"action_type": "0"}


def connection_pk_fields(biz_session_id: str):
    return {"biz_session_id": biz_session_id, "mutipk_type": "0"}


def mute_fields(biz_session_id: str, target_uid: int, *, media: str,
                remote: bool, muted: bool, room_id: int = 0):
    # PC 1v1 has no evidenced local-video HTTP Mute operation. Keep the
    # pre-existing video-PK publisher control on its separate RTC path.
    if media == "video" and not remote:
        raise PkProtocolError("不支持本端视频业务静音")
    result = {"biz_session_id": biz_session_id, "target_uid": f"{target_uid:d}",
              "mute_control_type": "2" if remote else "1",
              "connect_type": {"audio": "1", "video": "2"}[media],
              "active": "1" if muted else "0"}
    if not remote and room_id > 0:
        result["room_id"] = str(room_id)
    return result


def cancel_video_invite_fields(peer_search: int):
    # Ordinary ReqCancelInvitePk: room_id argument=0, omitted by constructor
    # secret:3aeda3..3aeda6. biz_session_id is inserted even when empty.
    return {"peer_uid": f"{peer_search:d}", "action": "3", "action_type": "1",
            "source": "0", "biz_session_id": ""}


def handle_invitation_fields(event, *, accept: bool, room_id=0):
    peer_search = event.selected_peer_uid
    if peer_search <= 0:
        raise PkProtocolError("邀请上下文缺少对方 UID")
    result = {"peer_uid": f"{peer_search:d}", "action": "1" if accept else "2",
              "action_type": "1",
              "biz_session_id": event.biz_session_id or "",
              "source": str(event.handle_source)}
    if room_id > 0:
        result["room_id"] = str(room_id)
    return result


def exit_pk_fields(*, end_round: bool):
    # Ordinary menu branch supplies anchor_uid0, so its constructor omits it.
    return {"stop_pk": "1" if end_round else "0"}


def cancel_match_fields(identity, kind: NativePkType, *, need_warn=False,
                        group_battle=False):
    sub_type = {NativePkType.MULTI: 100, NativePkType.MULTI_GROUP: 101,
                NativePkType.MULTI_RANDOM: 102, NativePkType.DOUBLE_BATTLE: 7,
                NativePkType.DOUBLE_BOUNTY_GAME: 89,
                NativePkType.MULTI_RELAY: 105}.get(kind, 0)
    if kind is NativePkType.CHATROOM_GROUP:
        sub_type = 104 if group_battle else 103
    warn = need_warn and kind in (NativePkType.DOUBLE_RANDOM,
                                        NativePkType.DOUBLE_BATTLE)
    return match_fields(identity, kind) | {"sub_type": str(sub_type),
                                           "need_warn": "1" if warn else "0"}


def parse_continuous_status(data):
    if not isinstance(data, dict):
        raise PkProtocolError("连续 PK 状态响应无效")
    status, disabled = data.get("status"), data.get("button_disable")
    versions, effect = data.get("pk_version"), data.get("effect_pk_version")
    toast = data.get("toast", "")
    # The server's disabled, unselected snapshot returns an explicit null.
    # It has no enabled families; do not infer a current or future PK mode.
    if "pk_version" in data and versions is None and status == 0 and effect == 0:
        versions = []
    if (type(status) is not int or type(disabled) is not bool or
            not isinstance(versions, list) or any(
                type(v) is not int for v in versions) or
            type(effect) is not int or not isinstance(toast, str)):
        raise PkProtocolError("连续 PK 状态字段无效")
    return PkContinuousStatus(status, disabled, toast, tuple(versions), effect)
