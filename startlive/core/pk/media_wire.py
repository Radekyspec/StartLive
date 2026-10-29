"""SLPK v2: shared-video setup/notifications and inline PCM; never raw video."""
from dataclasses import dataclass
from struct import unpack

from startlive.core.constant.pk_media import HEADER
from startlive.core.exceptions import PkProtocolError
from startlive.core.pk.states.session import MediaPacket


def select_capture(connection, *, audio=True, video=True):
    """Select raw streams before the plugin allocates capture resources."""
    mask = int(bool(audio)) | (int(bool(video)) << 1)
    if not mask:
        raise ValueError("At least one OBS capture stream must be enabled")
    request = b"SLPC" + bytes((1, mask, 0, 0))
    connection.write_exact(request)
    expected = b"SLPA" + request[4:]
    response = connection.read_exact(8)
    if response != expected:
        raise PkProtocolError(
            "OBS PK 插件采集选择响应不符，请更新插件并重启 OBS："
            f"expected={expected.hex()}, received={response.hex()}")


@dataclass(frozen=True, slots=True)
class SharedVideoSetup:
    token: str


@dataclass(frozen=True, slots=True)
class VideoNotice:
    sequence: int


def read_packet(connection):
    """Read and validate one complete SLPK message from the capture transport."""
    raw = connection.read_exact(HEADER.size)
    if len(raw) != HEADER.size:
        raise PkProtocolError(
            f"OBS frame header is incomplete: received {len(raw)}/{HEADER.size} bytes")
    magic, version, kind, flags, size, stamp, width, height, rate, frames = HEADER.unpack(
        raw)
    if magic != b"SLPK" or version != 2 or flags:
        raise PkProtocolError(
            "OBS media protocol mismatch; update both StartLive and its OBS plugin: "
            f"magic={magic!r}, version={version} (expected 2), flags={flags:#x}")
    if kind == 2:
        valid = not width and not height and rate == 48000 and 0 < frames <= 4800 and size == frames * 4
    else:
        valid = kind in (1, 3) and size == (8 if kind == 1 else 32) and not any(
            (stamp, width, height, rate, frames))
    if not valid:
        raise PkProtocolError(
            f"Invalid OBS media header: kind={kind}, size={size}, timestamp={stamp}, "
            f"dimensions={width}x{height}, sample_rate={rate}, frames={frames}")
    payload = connection.read_exact(size)
    if len(payload) != size:
        raise PkProtocolError(
            f"OBS media payload is incomplete: kind={kind}, received {len(payload)}/{size} bytes")
    if kind == 3:
        if any(value not in b"0123456789abcdef" for value in payload):
            raise PkProtocolError("Invalid OBS shared memory identifier")
        return SharedVideoSetup(payload.decode("ascii"))
    if kind == 1:
        sequence, = unpack("<Q", payload)
        if not sequence:
            raise PkProtocolError("Invalid OBS frame sequence: expected a positive value, received 0")
        return VideoNotice(sequence)
    return MediaPacket(kind, stamp, width, height, rate, frames, payload)
