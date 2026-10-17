"""Bind a supplied JOIN ticket to the logged-in user and current device."""
from .events import accepts_join_buvid
from .rtc_wire import decode_ticket
from startlive.core.pk.states.session import PkIdentity, RtcTicket
from startlive.core.pk.states.events import PkJoinEvent
from startlive.core.exceptions import PkAuthenticationError, PkProtocolError


def ticket_from_join(event: PkJoinEvent, identity: PkIdentity, *,
                     local_buvid: str,
                     cookie_buvid3: str) -> RtcTicket | None:
    if not accepts_join_buvid(event.buvid or "", local_buvid=local_buvid,
                              cookie_buvid3=cookie_buvid3):
        return None
    if event.uid != identity.uid:
        raise PkAuthenticationError("RTC 入会事件与当前登录用户不符")
    channel = event.rtc_channel_id
    if not channel or not channel.isascii() or not channel.isdecimal() or int(
            channel) <= 0:
        raise PkProtocolError("RTC 入会事件缺少有效的频道 ID")
    if not event.join_token:
        raise PkProtocolError(
            "RTC 入会事件未携带连接凭据，需要通过已验证的取票流程获取")
    # This is already Base64(AccessToken), not its opaque inner token field.
    decode_ticket(event.join_token, uid=identity.uid, channel_id=int(channel))
    return RtcTicket(int(channel), identity.uid, event.join_token)
