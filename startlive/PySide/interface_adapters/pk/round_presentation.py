"""Presentation-only round snapshot and countdown; no business transitions."""
from math import ceil

from startlive.core.constant.pk_info import NativePkState
from startlive.core.pk.pk_display import build_round_display


class PkRoundPresentation:
    def __init__(self, session):
        self.session = session
        self.info = self.peer_uid = None
        self.ended = False
        self.clock_key = self.deadline = self.remaining = None

    def render(self):
        session = self.session
        if session.closed:
            return
        round_id = (self.info.basic.pk_id if self.ended and self.info else
                    session.round_state.round_id if session.round_state.state != NativePkState.IDLE else 0)
        key = (id(self.info), session.round_state.state, round_id, self.ended)
        if key != self.clock_key:
            self.clock_key = key
            info = self.info
            seconds = (
                info.countdown_seconds if info is not None and info.basic.pk_id == round_id
                                          and not self.ended
                                          and session.round_state.state in (
                                              NativePkState.PKING,
                                              NativePkState.PUNISHING)
                else None)
            # Contracts48/49 supply a duration, not a Unix timestamp. A fresh
            # accepted snapshot resynchronizes this presentation-only clock.
            self.deadline = session._clock() + seconds if seconds is not None else None
        self.remaining = self.remaining_seconds()
        session.view.set_round_info(build_round_display(self.info,
                                                        state=session.round_state.state,
                                                        round_id=round_id,
                                                        own_uid=session.identity.uid,
                                                        own_room_id=session.identity.room_id,
                                                        remaining_seconds=self.remaining,
                                                        peer_search=self.peer_uid,
                                                        candidate=session.options.candidate,
                                                        ended=self.ended))

    def remaining_seconds(self):
        session = self.session
        return (max(0, ceil(self.deadline - session._clock()))
                if self.deadline is not None else None)
