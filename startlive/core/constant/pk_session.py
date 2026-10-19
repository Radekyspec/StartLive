from enum import StrEnum


class RtcMediaStage(StrEnum):
    JOINED = "joined"
    CONNECTED = "connected"
    PUBLISHED = "published"
    SUBSCRIBED = "subscribed"
    MEDIA_READY = "media_ready"
    CLOSED = "closed"
