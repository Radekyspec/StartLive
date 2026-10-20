from enum import IntEnum, StrEnum


class PkMode(StrEnum):
    TRADITIONAL = "traditional"
    VIDEO = "video"
    VIDEO_LINK = "video_link"


class NativePkType(IntEnum):
    """LiveHime controller types, distinct from HTTP pk_version/battle_type."""
    MULTI = 1
    MULTI_GROUP = 2
    MULTI_RANDOM = 3
    DOUBLE_RANDOM = 4
    DOUBLE_INVITE = 5
    DOUBLE_BATTLE = 6
    DOUBLE_GAME = 7
    DOUBLE_BOUNTY_GAME = 8
    DOUBLE_CLASSIC = 9
    CHATROOM_CLASSIC = 10
    DOUBLE_RANDOM_CONNECT = 11
    CHATROOM_GROUP = 12
    MULTI_RELAY = 13

    @property
    def server_type(self) -> int:
        # Native GetServerPkType, verified in contract-2. Not invitation/action values.
        return {1: 8, 2: 8, 3: 8, 4: 2, 5: 6, 6: 2, 7: 2,
                8: 6, 9: 1, 10: 1, 11: 10000, 12: 8, 13: 8}[self.value]


class PkPhase(StrEnum):
    IDLE = "idle"
    PREPARING = "preparing"
    MATCHING = "matching"
    INVITING = "inviting"
    CONNECTING = "connecting"
    ACTIVE = "active"
    STOPPING = "stopping"
    FINISHED = "finished"
    FAILED = "failed"


class NativeInteractionState(IntEnum):
    """Contract19 native connection log labels; distinct from PkPhase."""
    READY = 0
    WAITING_JOIN = 1
    CONNECTING = 2
    STOPPING = 3
