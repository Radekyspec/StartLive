"""Contract17 ordinary business2 member/publication reconciliation.

The caller must establish the current room-info context and the SDK publication
callback first. Neither JoinResp.users nor arbitrary Goim messages are such a
callback. Native state2 is retained as a raw value, not renamed to ACTIVE.
"""
from copy import deepcopy

from startlive.core.pk.states.peers import PkMediaPreference, PkRemoteMember, \
    RtcSubscription
from startlive.core.exceptions import PkProtocolError


def default_media_preference(default_sub_mode):
    """Base settings only; explicit member/local overrides remain authoritative."""
    if type(default_sub_mode) is not int or default_sub_mode not in (0, 1, 2,
                                                                     3):
        raise PkProtocolError("尚未确认的 RTC 默认订阅模式")
    return PkMediaPreference(audio_muted=not bool(default_sub_mode & 1),
                             video_muted=not bool(default_sub_mode & 2))


def room_info_members(data, *, default_sub_mode, preferences=None):
    """Project an already validated room-info data object, not a Goim event.

    Only members[].uid is used for identity. The caller supplies independently
    established local/business overrides; unknown member fields stay in raw.
    This projection does not establish which interaction the payload belongs to.
    """
    if not isinstance(data, dict) or not isinstance(data.get("members"), list):
        raise PkProtocolError("连线房间信息缺少成员列表")
    default = default_media_preference(default_sub_mode)
    overrides, members = preferences or {}, []
    for item in data["members"]:
        uid = item.get("uid") if isinstance(item, dict) else None
        if isinstance(uid, str) and uid.isascii() and uid.isdecimal():
            uid = int(uid)
        if type(uid) is not int or not 0 < uid < 1 << 64:
            raise PkProtocolError("连线房间成员缺少有效 UID")
        members.append(
            PkRemoteMember(uid, overrides.get(uid, default), deepcopy(item)))
    return tuple(members)


class PkPeerRegistry:
    """A registry per interaction, with no unknown-user fallback or UID guessing.

    Scope equality and duplicate desired-subscription suppression are explicit
    StartLive policies. Exact native event version/session guards are pending.
    Returned values describe desired subscriptions; this object sends no RPCs.
    """

    def __init__(self, own_uid, scope):
        if own_uid <= 0 or not scope.biz_session_id or not scope.rtc_channel_id:
            raise PkProtocolError("对手列表缺少当前账号或连线会话信息")
        self.own_uid, self.scope = own_uid, scope
        self.members, self.publications = {}, {}
        self._emitted = {}

    def add_member(self, member, *, scope):
        if not self._accepts(member.uid, scope):
            return None
        self.members[member.uid] = member
        return self._reconcile(member.uid)

    def on_publication(self, publication, *, scope, native_state):
        if native_state != 2 or not self._accepts(publication.uid, scope):
            return None
        # OnUserPub itself only inserts a previously absent UID. Publication
        # flags do not override the business user's mute preferences.
        self.publications.setdefault(publication.uid, publication)
        return self._reconcile(publication.uid)

    def _accepts(self, uid, scope):
        return scope == self.scope and type(
            uid) is int and uid > 0 and uid != self.own_uid

    def _reconcile(self, uid):
        member = self.members.get(uid)
        if member is None or uid not in self.publications:
            return None
        preference = member.preference
        desired = RtcSubscription(uid, video=not preference.video_muted,
                                  audio=not preference.audio_muted)
        if self._emitted.get(uid) == desired:
            return None
        self._emitted[uid] = desired
        return desired

    def clear(self):
        """Reset after local interaction teardown; not on PK_BATTLE_END alone."""
        self.members.clear()
        self.publications.clear()
        self._emitted.clear()
