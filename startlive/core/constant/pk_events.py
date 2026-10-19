"""Confirmed business-event projections; raw payloads preserve unexpanded fields."""

EVENT_TYPES = {
    "UNIVERSAL_INTERACT_STREAM_CONTROL",
    "UNIVERSAL_INTERACT_INVITATION", "UNIVERSAL_INTERACT_JOIN",
    "UNIVERSAL_INTERACT_OPERATION", "UNIVERSAL_INTERACT_LEAVE", "PK_BATTLE_END",
    "PK_BATTLE_PRE", "PK_BATTLE_START", "PK_BATTLE_MATCH_TIMEOUT", "PK_INFO",
}

# Observed before PK_INFO in the user's outgoing-invitation log. Its native
# parser/receiver relationship remains unverified; logging is not dispatch.
OBSERVED_ONLY_COMMANDS = frozenset({"PK_BATTLE_PRE_NEW"})
