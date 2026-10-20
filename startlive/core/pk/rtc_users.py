"""Contract18 SDK user transitions, separate from PK business membership."""
from copy import deepcopy
from dataclasses import replace

from startlive.core.exceptions import PkProtocolError
from startlive.core.pk.states.peers import RtcStream, RtcUserEvent, RtcUserState


def _stream(value):
    value = value if isinstance(value, dict) else {}
    return RtcStream(
        **{key: value[key] for key in RtcStream.__dataclass_fields__ if
           key in value})


class RtcUserRegistry:
    def __init__(self, emit):
        self.users = {}
        self.emit = emit
        self.initialized = False

    def initialize(self, members):
        """Fresh MembersResp only; repeated snapshot reconciliation is unproved."""
        if self.initialized or self.users:
            raise PkProtocolError("当前尚未支持重复刷新 RTC 成员快照")
        self.initialized = True
        for user in members:
            state = self._join(user)
            if state is not None and state.published:
                self.emit(RtcUserEvent("published", state.uid, state.stream))

    def _join(self, user):
        uid = user.get("uid", 0)
        if uid <= 0:
            raise PkProtocolError("RTC 成员缺少有效 UID")
        if uid in self.users:
            return None
        state = RtcUserState(uid, user.get("role", 0), "stream" in user,
                             _stream(user.get("stream")), deepcopy(user))
        self.users[uid] = state
        self.emit(RtcUserEvent("joined", uid))
        return state

    def consume(self, message):
        """True means a promoted SDK user notification, not a business event."""
        if "join_notify" in message:
            # JoinNotify with a present stream sets published but emits ONLY
            # joined. A subsequent PubNotify then updates without re-emitting.
            self._join(message["join_notify"].get("user", {}))
        elif "pub_notify" in message:
            event = message["pub_notify"]
            uid = event.get("uid", 0)
            state = self.users.get(uid) or self._join({"uid": uid})
            updated = replace(state, published=True,
                              stream=_stream(event.get("stream")))
            self.users[uid] = updated
            if not state.published:
                self.emit(RtcUserEvent("published", uid, updated.stream))
        elif "mute_notify" in message:
            event = message["mute_notify"]
            uid = event.get("uid", 0)
            state = self.users.get(uid)
            arm = next(
                (key for key in ("audio_muted", "video_muted") if key in event),
                None)
            if state is not None and state.published and arm is not None:
                updated = replace(state, stream=replace(state.stream,
                                                        **{arm: event[arm]}))
                # Contract32: cache first, callback second, including repeated
                # values. This is metadata, not a local capture/subscription command.
                self.users[uid] = updated
                self.emit(RtcUserEvent(arm, uid, updated.stream,
                                       event.get("reason_raw", 0)))
        elif "un_pub_notify" in message:
            uid = message["un_pub_notify"].get("uid", 0)
            state = self.users.get(uid)
            if state is not None and state.published:
                self.users[uid] = replace(state, published=False)
                self.emit(RtcUserEvent("unpublished", uid))
        elif "leave_notify" in message:
            event = message["leave_notify"]
            uid = event.get("uid", 0)
            if self.users.pop(uid, None) is not None:
                # Do not invent an external unpublished event or business END.
                self.emit(RtcUserEvent("left", uid,
                                       reason_raw=event.get("reason_raw", 0)))
        else:
            return False
        return True

    def clear(self):
        self.users.clear()
        self.initialized = False
