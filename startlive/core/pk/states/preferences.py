from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PkPreferenceValues:
    """Confirmed application values; duration uses the server's option key."""

    duration: int
    accept_pk: bool
    accept_unfollowed_pk: bool
    classic_pk: bool
    classic_opponent_voice: bool
    accept_connection: bool
    mutual_only: bool
    allow_apply_join: bool
    allow_auto_join: bool
    allow_other_invite: bool
