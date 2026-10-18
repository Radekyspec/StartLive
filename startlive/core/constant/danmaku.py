from enum import StrEnum


class DanmakuState(StrEnum):
    CONNECTING = "connecting"
    AUTHENTICATED = "authenticated"
    RECONNECTING = "reconnecting"
    REFRESHING_TOKEN = "refreshing_token"
