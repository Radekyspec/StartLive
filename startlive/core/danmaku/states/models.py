from dataclasses import dataclass, field

from startlive.core.identity import AccountIdentity


@dataclass(frozen=True, slots=True)
class DanmakuBootstrap:
    """Chosen bootstrap endpoint and token; header/cookie policy lives upstream."""
    host: str
    port: int
    key: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class DanmakuLoginSettings:
    """One Goim context; preserve queue_uuid across ordinary reconnects."""
    build: int
    buvid: str = field(repr=False)
    version_name: str
    device: str
    osver: str
    support_ack: bool
    queue_uuid: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class DanmakuPacket:
    version: int
    operation: int
    sequence: int
    payload: bytes = field(repr=False)


DanmakuIdentity = AccountIdentity


@dataclass(frozen=True, slots=True)
class DanmakuMessage:
    command: str
    sequence: int
    envelope: dict = field(repr=False)


@dataclass(frozen=True, slots=True)
class DanmakuResult:
    operation: str
    data: object = field(repr=False)
