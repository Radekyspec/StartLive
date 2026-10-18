"""Business parameters confirmed by native callers, separate from HTTP signing."""
from startlive.core.pk.states.session import PkContinuousStatus
from startlive.core.constant.pk import NativePkType
from startlive.core.exceptions import PkProtocolError


def precheck_fields(identity, kind: NativePkType):
    return {"room_id": str(identity.room_id),
            "pk_version": str(kind.server_type),
            "mobi_app": "pc_link"}


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
    if type(enabled) is not bool:
        raise TypeError("enabled must be a boolean")
    return {"ruid": str(identity.uid), "status": "1" if enabled else "0",
            "pk_version": str(kind.server_type), "client_traceid": trace_id}


def video_invite_fields(peer_search: int, *, invited_type_label: str):
    """Directed video PK search: native5 -> precheck6 -> startMutiPK4.

    The chosen Search response row supplies data.users[].label_type. It is
    distinct from both the query category and the candidate's display label.
    """
    if type(peer_search) is not int or peer_search <= 0:
        raise PkProtocolError("视频 PK 邀请需要有效的对方 UID")
    if not isinstance(invited_type_label, str):
        raise PkProtocolError("视频 PK 邀请标签必须来自候选人的字符串字段")
    result = {"mutipk_type": "4", "invite_uid": str(peer_search),
              "invited_type": "1"}
    if invited_type_label:
        result["invited_type_label"] = invited_type_label
    return result


def cancel_video_invite_fields(peer_search: int):
    if type(peer_search) is not int or peer_search <= 0:
        raise PkProtocolError("取消邀请需要有效的对方 UID")
    # Ordinary ReqCancelInvitePk: room_id argument=0, omitted by constructor
    # secret:3aeda3..3aeda6. biz_session_id is inserted even when empty.
    return {"peer_uid": str(peer_search), "action": "3", "action_type": "1",
            "source": "0", "biz_session_id": ""}


def handle_invitation_fields(context, *, accept: bool, room_id=0):
    if type(accept) is not bool:
        raise PkProtocolError("邀请操作必须明确为接受或拒绝")
    peer_search = context.selected_peer_uid
    if peer_search <= 0:
        raise PkProtocolError("邀请上下文缺少对方 UID")
    result = {"peer_uid": str(peer_search), "action": "1" if accept else "2",
              "action_type": "1",
              "biz_session_id": context.biz_session_id,
              "source": str(context.source)}
    if room_id > 0:
        result["room_id"] = str(room_id)
    return result


def exit_pk_fields(*, end_round: bool):
    if type(end_round) is not bool:
        raise PkProtocolError("请明确是否同时结束这一轮 PK")
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
    warn = bool(need_warn) and kind in (NativePkType.DOUBLE_RANDOM,
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
