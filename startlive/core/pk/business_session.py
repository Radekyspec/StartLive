"""Contract19 ordinary business2 JOIN admission and server LEAVE reaction."""
from startlive.core.constant.pk import NativeInteractionState
from startlive.core.exceptions import PkError
from startlive.core.pk.states.events import PkLeaveEvent, PkLocalQuit
from .video_eligibility import interaction_business_type


def require_business_join(event, *, native_state, eligibility):
    if interaction_business_type(event) not in (1, 2):
        raise PkError("此 JOIN 的业务标签、视频模板或画面尺寸尚不受支持")
    if eligibility is None or eligibility.allowed is not True:
        raise PkError((
                          eligibility.reason if eligibility else "") or "当前尚不能确认是否可加入此连线")
    if native_state != NativeInteractionState.READY:
        raise PkError("当前连线尚未退出，不能加入新的连线")
    if not event.rtc_channel_id:
        raise PkError("连线信息缺少 RTC 频道")


def local_quit_from_business_leave(event, *, rtc_channel_id, native_state,
                                   business_label=None):
    if not isinstance(event,
                      PkLeaveEvent) or native_state == NativeInteractionState.READY:
        return None
    # 114 names its business family. An absent label is tolerated for older
    # captures; an explicit different label must never tear down this room.
    if business_label and event.biz_label and event.biz_label != business_label:
        return None
    # Native compares channel strings exactly. Rejecting an empty stored
    # identity is a stricter StartLive policy; no UID/session equality is added.
    if not rtc_channel_id or event.rtc_channel_id != rtc_channel_id:
        return None
    return PkLocalQuit({1: 30, 2: 31, 3: 32}.get(event.close_user_reason, 30),
                       event.toast or "")
