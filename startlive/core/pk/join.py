"""Fixed JOIN admission: device, ticket, duplicate, business and local readiness."""
from startlive.core.constant.pk import NativeInteractionState
from startlive.core.exceptions import PkAuthenticationError, PkError, PkProtocolError
from startlive.core.pk.events import accepts_join_buvid
from startlive.core.pk.rtc_wire import decode_ticket
from startlive.core.pk.video_eligibility import interaction_business_type


def prepare_join(event, identity, *, current_key, retired_channels,
                 native_state, blocked_reason):
    """Return (ticket, publication), or None for another device/retired/duplicate JOIN.

    The RTC owner installs the key only while starting its worker and rolls it
    back on startup failure. A reconnect flag never bypasses that ownership.
    """
    if (event.biz_session_id, event.rtc_channel_id) in retired_channels:
        return None
    if not accepts_join_buvid(event.buvid or "", local_buvid=identity.buvid,
                             cookie_buvid3=dict(identity.cookies).get("buvid3", "")):
        return None
    if event.uid != identity.uid:
        raise PkAuthenticationError("RTC 入会事件与当前登录用户不符")
    channel = event.rtc_channel_id
    if not channel or not channel.isascii() or not channel.isdecimal() or int(channel) <= 0:
        raise PkProtocolError("RTC 入会事件缺少有效的频道 ID")
    if not event.join_token:
        raise PkProtocolError("RTC 入会事件未携带连接凭据，需要通过已验证的取票流程获取")
    ticket = decode_ticket(event.join_token, uid=identity.uid, channel_id=int(channel))
    key = (event.biz_session_id, channel, identity.uid, event.join_token)
    if current_key == key:
        return None
    if current_key is not None:
        raise PkProtocolError("收到新的 RTC 入会信息，需要先完成当前连接的退出或重连")
    if interaction_business_type(event) not in (1, 2):
        raise PkError("此 JOIN 的业务标签、视频模板或画面尺寸尚不受支持")
    if blocked_reason is not None:
        raise PkError(blocked_reason)
    if native_state != NativeInteractionState.READY:
        raise PkError("当前连线尚未退出，不能加入新的连线")
    control = event.stream_control.get("pub_sub_control", {})
    if not isinstance(control, dict):
        raise PkProtocolError("JOIN 发布控制格式无效")
    status = control.get("pub_status", 1)  # Native default: audio only.
    if type(status) is not int or status not in (0, 1, 2, 3):
        raise PkProtocolError(f"JOIN 发布模式尚不受支持：{status!r}")
    publication = frozenset(
        media for media, enabled in (("audio", status in (1, 3)),
                                     ("video", status in (2, 3))) if enabled)
    return ticket, publication
