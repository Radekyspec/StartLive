"""Contract21 state reconciliation; no HTTP, RTC or GUI side effects.

Contract24 supplies the response type mapper and idle eligibility rules.
Callers supply local readiness facts independently of this verified status map.
Round/session binding and preservation of the timestamp across local cleanup
are explicit StartLive policies. Create a new owner for a new flow epoch.
"""
from startlive.core.constant.pk import NativePkType
from startlive.core.constant.pk_info import STATUS_STATES, NativePkState, \
    PkInfoAction
from startlive.core.constant.pk_info import VIDEO_STATUS_STATES
from startlive.core.pk.states.info import PkInfoDecision
from .pk_eligibility import pk_start_eligibility, pk_type_from_server


class PkRoundState:
    def __init__(self, kind, *, accepts_type=None, idle_eligibility=None,
                 state=NativePkState.IDLE, round_id=0, biz_session_id="",
                 last_ended_round_id=0,
                 start_state_provider=None):
        self.kind = NativePkType(kind)
        self.state = NativePkState(state)
        self.accepts_type, self.idle_eligibility = accepts_type, idle_eligibility
        self.start_state_provider = start_state_provider
        self.round_id, self.biz_session_id = round_id, biz_session_id
        self.last_ended_round_id = last_ended_round_id
        self.timestamp, self.info = 0, None
        self.flag3d0_unknown = False

    def _decision(self, action, info, reason="", previous_state=None):
        return PkInfoDecision(action, info,
                              self.state if previous_state is None else previous_state,
                              self.state, reason)

    def _type_allowed(self, info):
        mapped = pk_type_from_server(info.basic.type, info.basic.sub_type)
        return mapped is not None and (
                    self.accepts_type is None or self.accepts_type(
                info.basic) is True)

    def _idle_allowed(self, info):
        if self.start_state_provider is not None:
            mapped = pk_type_from_server(info.basic.type, info.basic.sub_type)
            decision = pk_start_eligibility(mapped, self.start_state_provider())
            if decision.allowed is not True:
                return False
            return self.idle_eligibility is None or self.idle_eligibility(
                info) is True
        return self.idle_eligibility is not None and self.idle_eligibility(
            info) is True

    def _belongs(self, info):
        if self.round_id and info.basic.pk_id != self.round_id:
            return False
        # The legacy converter explicitly clears biz_session_id; it cannot
        # establish or replace a business interaction context.
        return not (not info.legacy and self.biz_session_id
                    and info.basic.biz_session_id != self.biz_session_id)

    def from_push(self, info):
        if self.state <= NativePkState.PREPARING and info.basic.status >= 1001:
            return self._decision(PkInfoAction.IGNORED, info,
                                  "terminal_before_round")
        if not self._belongs(info):
            return self._decision(PkInfoAction.IGNORED, info,
                                  "different_round_or_session")
        if self.state == NativePkState.IDLE:
            if info.basic.pk_id == self.last_ended_round_id:
                return self._decision(PkInfoAction.IGNORED, info,
                                      "already_ended")
            if not self._type_allowed(info) or not self._idle_allowed(info):
                return self._decision(PkInfoAction.BLOCKED, info,
                                      "尚未确认是否可以接管此 PK 回合")
            if info.basic.pk_id <= 0:
                return self._decision(PkInfoAction.BLOCKED, info,
                                      "PK 状态缺少有效回合 ID")
            self.round_id = info.basic.pk_id
            # Contract21 idle listener installs the mapped type before query.
            self.kind = pk_type_from_server(info.basic.type,
                                            info.basic.sub_type)
            # The native idle listener queries; it does not directly install
            # the incoming DTO/timestamp or announce a running PK.
            return self._decision(PkInfoAction.QUERY, info)
        return self.apply(info)

    def apply(self, info):
        basic = info.basic
        if (info.source_kind == 3 and self.state >= NativePkState.MATCHING
                and not any(
                    (info.timestamp, basic.status, info.match.match_status,
                     basic.type, basic.sub_type))):
            # Native has an error counter here. Its unverified eventual action
            # is not imitated; an empty legacy response cannot end a round.
            return self._decision(PkInfoAction.IGNORED, info,
                                  "empty_legacy_response")
        if info.timestamp <= self.timestamp:
            return self._decision(PkInfoAction.IGNORED, info, "stale_timestamp")
        if not self._belongs(info):
            return self._decision(PkInfoAction.IGNORED, info,
                                  "different_round_or_session")
        if not self._type_allowed(info):
            return self._decision(PkInfoAction.BLOCKED, info,
                                  "尚未确认此 PK 类型的状态映射")
        if self.state == NativePkState.IDLE and basic.status >= 1001:
            return self._decision(PkInfoAction.IGNORED, info, "idle_terminal")
        previous = self.state
        self.info, self.timestamp = info, info.timestamp
        # Contract25: accepted common DTO replaces current kind. Request intent
        # belongs to the session; a kind change alone has no RTC side effect.
        self.kind = pk_type_from_server(basic.type, basic.sub_type)
        self.round_id = basic.pk_id or self.round_id
        self.flag3d0_unknown = basic.status in (301, 501, 602)
        action = PkInfoAction.UPDATED
        statuses = STATUS_STATES if info.legacy else VIDEO_STATUS_STATES
        if (basic.status >= 1001 if info.legacy else basic.status == 1401):
            action = PkInfoAction.ROUND_ENDED
        elif basic.status == 0:
            if info.match.match_status == 0:
                action = PkInfoAction.ROUND_IDLE
            elif info.match.match_status == 1:
                if not (
                        self.kind == NativePkType.MULTI_RANDOM and previous == NativePkState.PREPARING):
                    self.state = NativePkState.MATCHING
        elif basic.status in statuses:
            self.state = statuses[basic.status]
        if action in (PkInfoAction.ROUND_IDLE, PkInfoAction.ROUND_ENDED):
            self.last_ended_round_id = self.round_id
            self.state = NativePkState.IDLE
            self.round_id = 0
        return self._decision(action, info, previous_state=previous)

    def quit_round(self):
        """Classic6204 Not Matching quits local round state without RTC work."""
        if self.round_id:
            self.last_ended_round_id = self.round_id
        self.round_id = 0
        self.state = NativePkState.IDLE
