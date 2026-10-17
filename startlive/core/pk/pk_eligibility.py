"""Contract24 forward PK type mapper and distinct idle-start eligibility."""
from startlive.core.pk.states.eligibility import PkStartEligibility
from startlive.core.constant.pk import NativePkType
from startlive.core.constant.pk_info import NativePkState


def pk_type_from_server(server_type, sub_type):
    """Actual response mapping, never the inverse of request server_type."""
    if any(type(value) is not int or not -(1 << 31) <= value < 1 << 31 for value
           in (server_type, sub_type)):
        return None
    if server_type == 1:
        # StartLive has no voice-room or viewer-microphone business. The native
        # context-specific chatroom alternative is outside this PK session.
        return NativePkType.DOUBLE_CLASSIC
    if server_type == 2:
        return NativePkType.DOUBLE_BATTLE if sub_type == 7 else NativePkType.DOUBLE_RANDOM
    if server_type == 6:
        return NativePkType.DOUBLE_BOUNTY_GAME if sub_type == 89 else NativePkType.DOUBLE_INVITE
    if server_type == 8:
        return {100: NativePkType.MULTI, 101: NativePkType.MULTI_GROUP,
                102: NativePkType.MULTI_RANDOM,
                103: NativePkType.CHATROOM_GROUP,
                104: NativePkType.CHATROOM_GROUP,
                105: NativePkType.MULTI_RELAY}.get(sub_type)
    return None


def pk_start_eligibility(kind, facts, *, continuous_video=False):
    """Use for starting/adopting an idle round, never for active updates."""
    if facts is None or facts.output_ready is None:
        return PkStartEligibility(None, "尚未确认直播输出是否就绪")
    if facts.output_ready is not True:
        return PkStartEligibility(False, "直播输出尚未就绪")
    # Contract27 fifth_flag=true skips this branch only for automatic video
    # matching. It does not bypass output_ready or the remaining local gates.
    if not (continuous_video and kind == NativePkType.DOUBLE_RANDOM):
        if facts.live_output_active is None:
            return PkStartEligibility(None, "尚未确认当前直播输出状态")
        if facts.live_output_active is not True:
            return PkStartEligibility(False, "请先开始直播再进行 PK")
    if facts.voice_microphone_available is None:
        return PkStartEligibility(None, "尚未确认语音麦克风是否可用")
    if facts.voice_microphone_available is not True:
        return PkStartEligibility(False, "当前语音麦克风状态不允许开始 PK")
    if facts.pk_state is None:
        return PkStartEligibility(None, "尚未确认当前 PK 状态")
    if facts.pk_state != NativePkState.IDLE:
        return PkStartEligibility(False, "当前 PK 尚未结束，不能开始新回合")
    return PkStartEligibility(True)
