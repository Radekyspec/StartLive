"""Contract23 ordinary video business2 eligibility with explicit local facts."""
from startlive.core.constant.pk import NativeInteractionState, NativePkType
from startlive.core.constant.pk_info import NativePkState
from startlive.core.pk.states.events import PkInvitationEligibility, \
    PkJoinEligibility


def interaction_business_type(event):
    """JOIN business mapper, distinct from PK_INFO type/sub_type mapping."""
    if event.biz_label in ("classic_pk", "voice_conn", "multi_user_conn"):
        return {"classic_pk": 1, "voice_conn": 6, "multi_user_conn": 5}[
            event.biz_label]
    if event.biz_label != "universal_multi_conn":
        return 0
    scene = event.biz_extra.get("interact_scene_configuration")
    template = scene.get("interact_template") if isinstance(scene,
                                                            dict) else None
    if not isinstance(template, dict) or template.get("template_id") not in (
            "multi_conn_grid", "multi_conn_spotlight"):
        return 0
    layout = template.get("layout_data")
    if not isinstance(layout, dict) or any(
            type(layout.get(key)) is not int or not 0 < layout[key] < 1 << 31
            for key in ("width", "height")):
        return 0
    return 2


def video_eligibility(facts):
    """Relevant ordinary45ed50 checks using StartLive output/session facts.

    This helper may allow a same-business nonready interaction; common JOIN
    separately requires Ready, while ordinary invitation acceptance uses this
    helper before sending Handle. Unknown required facts stay blocked.
    """
    if facts is None or facts.output_ready is None:
        return PkJoinEligibility(None, "尚未确认直播输出是否就绪")
    if facts.output_ready is not True:
        return PkJoinEligibility(False, "直播输出尚未就绪")
    if facts.live_output_active is None:
        return PkJoinEligibility(None, "尚未确认当前直播输出状态")
    if facts.live_output_active is not True:
        return PkJoinEligibility(False, "请先开始直播再进行视频 PK")
    if facts.interaction_state is None:
        return PkJoinEligibility(None, "尚未确认当前连线状态")
    if facts.interaction_state != NativeInteractionState.READY:
        if facts.interaction_business is None:
            return PkJoinEligibility(None, "尚未确认当前连线业务类型")
        if facts.interaction_business != 2:
            return PkJoinEligibility(False, "当前已有其他类型的连线")
    if facts.pk_state is None:
        return PkJoinEligibility(None, "尚未确认当前 PK 回合状态")
    if NativePkState.PKING <= facts.pk_state <= NativePkState.FREEZING:
        return PkJoinEligibility(False, "当前 PK 回合阶段不允许加入视频连线")
    if facts.pk_state != NativePkState.IDLE and facts.pk_type is None:
        return PkJoinEligibility(None, "尚未确认当前 PK 回合类型")
    if facts.pk_state != NativePkState.IDLE and facts.pk_type == NativePkType.CHATROOM_CLASSIC:
        return PkJoinEligibility(False, "当前语音房 PK 尚未结束")
    return PkJoinEligibility(True)


def invitation_eligibility(facts):
    decision = video_eligibility(facts)
    return PkInvitationEligibility(decision.allowed, decision.reason)
