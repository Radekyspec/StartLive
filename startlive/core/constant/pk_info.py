from enum import IntEnum, StrEnum


class NativePkState(IntEnum):
    """Contract21 PK round states, independent of native interaction states."""
    IDLE = 0
    STARTING = 1
    MATCHING = 2
    SELECTING_USER = 3
    PREPARING = 4
    PKING = 5
    BUZZING = 6
    EXIT = 7
    FREEZING = 8
    PUNISHING = 9
    END = 10


class PkInfoAction(StrEnum):
    IGNORED = "ignored"
    BLOCKED = "blocked"
    QUERY = "query"
    UPDATED = "updated"
    ROUND_IDLE = "round_idle"
    ROUND_ENDED = "round_ended"


STATUS_STATES = {
    100: NativePkState.SELECTING_USER, 101: NativePkState.PREPARING,
    201: NativePkState.PKING, 301: NativePkState.BUZZING,
    304: NativePkState.EXIT,
    401: NativePkState.FREEZING, 404: NativePkState.FREEZING,
    501: NativePkState.FREEZING, 905: NativePkState.FREEZING,
    601: NativePkState.PUNISHING, 602: NativePkState.PUNISHING,
    610: NativePkState.PUNISHING,
}

VIDEO_STATUS_STATES = {
    101: NativePkState.PREPARING, 201: NativePkState.PKING,
    304: NativePkState.EXIT, 404: NativePkState.FREEZING,
}
