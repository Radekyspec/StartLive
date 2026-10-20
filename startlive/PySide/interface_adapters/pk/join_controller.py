from startlive.core.constant.pk import NativeInteractionState
from startlive.core.exceptions import PkProtocolError
from startlive.core.pk.business_session import require_business_join
from startlive.core.pk.identity import require_current_identity
from startlive.core.pk.join_ticket import ticket_from_join


class PkJoinController:
    """One guarded JOIN entry for HTTP and push, owned by one PK session.

    Exact duplicate suppression is StartLive policy. A changed token/session
    requires explicit teardown. Contract31's token-driven native reconnect
    requires matching interaction business3/4 and Connecting2; ordinary video
    PK business2 is excluded. A reconnect flag never bypasses this owner guard.
    """

    def __init__(self, identity, *, connect,
                 identity_guard=require_current_identity,
                 eligibility_check=None):
        self.identity, self.connect, self.identity_guard = identity, connect, identity_guard
        self.eligibility_check = eligibility_check
        self.native_state = NativeInteractionState.READY
        self._key = None
        self._retired_channels = set()

    def handle(self, event):
        self.identity_guard(self.identity)
        if (event.biz_session_id,
            event.rtc_channel_id) in self._retired_channels:
            return False
        ticket = ticket_from_join(event, self.identity,
                                  local_buvid=self.identity.buvid,
                                  cookie_buvid3=dict(self.identity.cookies).get(
                                      "buvid3", ""))
        if ticket is None:
            return False
        key = (event.biz_session_id, event.rtc_channel_id, ticket.uid,
               ticket.access_token)
        if self._key == key:
            return False
        if self._key is not None:
            raise PkProtocolError(
                "收到新的 RTC 入会信息，需要先完成当前连接的退出或重连")
        require_business_join(event, native_state=self.native_state,
                              eligibility=self.eligibility_check(
                                  event) if self.eligibility_check else None)
        self._key = key
        try:
            self.connect(ticket, event)
        except Exception:
            self._key = None
            raise
        return True

    def clear(self):
        """Call after the owning session has stopped its current RTC worker."""
        if self._key is not None:
            self._retired_channels.add(self._key[:2])
        self._key = None
        self.native_state = NativeInteractionState.READY
