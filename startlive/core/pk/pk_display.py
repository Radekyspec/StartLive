"""Contracts48/49 display projection from accepted round and member snapshots."""
from startlive.core.constant.pk import NativePkType
from startlive.core.constant.pk_info import NativePkState
from startlive.core.pk.pk_eligibility import pk_type_from_server
from startlive.core.pk.states.candidates import PkCandidate
from startlive.core.pk.states.display import PkRoundDisplay
from startlive.core.pk.states.info import PkInfo


def build_round_display(
        info: PkInfo | None,
        *,
        state: NativePkState,
        round_id: int | None,
        own_uid: int,
        own_room_id: int = 0,
        peer_search: int | None = None,
        candidate: PkCandidate | None = None,
        ended: bool = False,
        remaining_seconds: int | None = None,
) -> PkRoundDisplay:
    """The owner supplies its accepted snapshot and verified opponent UID.

    A search selection can name that opponent only after the UIDs match.
    Classic members can establish the peer after own UID/room identification.
    Video still requires the separately verified business-room peer UID.
    Passing no snapshot clears scores/results from any earlier attempt.
    """
    state = NativePkState(state)
    peer_search = peer_search if peer_search and peer_search > 0 and peer_search != own_uid else None
    members = info.members if info is not None else ()
    own_matches = [member for member in members if member.uid == own_uid
                   and (own_room_id <= 0 or member.room_id == own_room_id)]
    own = own_matches[0] if len(own_matches) == 1 else None
    remote = [member for member in members if
              member.uid > 0 and member.uid != own_uid
              and (own_room_id <= 0 or member.room_id != own_room_id)]
    if peer_search is not None:
        peer_matches = [member for member in remote if
                        member.uid == peer_search]
    elif (info is not None and own is not None
          and pk_type_from_server(info.basic.type,
                                  info.basic.sub_type) == NativePkType.DOUBLE_CLASSIC):
        peer_matches = remote
    else:
        peer_matches = []
    peer = peer_matches[0] if len(peer_matches) == 1 else None
    if peer is not None:
        peer_search = peer.uid
    peer_name = (peer.uname if peer is not None and peer.uname else
                 candidate.uname if candidate is not None and candidate.uid == peer_search else "")
    # Result activation is StartLive policy, not a full native lifecycle claim.
    show_result = ended or state in (NativePkState.FREEZING,
                                     NativePkState.PUNISHING, NativePkState.END)
    own_result = own.is_winner if own is not None and show_result and own.is_winner in (
        0, 1, 2) else None
    peer_result = peer.is_winner if peer is not None and show_result and peer.is_winner in (
        0, 1, 2) else None
    show_countdown = not ended and state in (NativePkState.PKING,
                                             NativePkState.PUNISHING)
    return PkRoundDisplay(
        round_id=round_id if round_id and round_id > 0 else None,
        state=state,
        own_uid=own_uid,
        status_message=info.basic.status_msg if info is not None else "",
        punish_text=info.basic.punish_text if info is not None else "",
        peer_search=peer_search,
        peer_name=peer_name,
        ended=ended,
        own_name=own.uname if own is not None else "",
        own_votes=own.votes if own is not None else None,
        own_votes_text=own.votes_text if own is not None else "",
        own_result=own_result,
        peer_votes=peer.votes if peer is not None else None,
        peer_votes_text=peer.votes_text if peer is not None else "",
        peer_result=peer_result,
        remaining_seconds=max(0,
                              remaining_seconds) if show_countdown and remaining_seconds is not None else None,
    )
