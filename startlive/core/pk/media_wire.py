"""SLPK v2: shared-video setup/notifications and inline PCM; never raw video."""
from dataclasses import dataclass
from struct import unpack

from startlive.core.pk.states.session import MediaPacket
from startlive.core.constant.pk_media import HEADER
from startlive.core.exceptions import PkProtocolError


@dataclass(frozen=True, slots=True)
class SharedVideoSetup:
    token: str


@dataclass(frozen=True, slots=True)
class VideoNotice:
    sequence: int


def parse_header(raw):
    if len(raw) != HEADER.size:
        raise PkProtocolError("OBS frame header is incomplete")
    magic, version, kind, flags, size, stamp, width, height, rate, frames = HEADER.unpack(
        raw)
    if magic != b"SLPK" or version != 2 or flags:
        raise PkProtocolError(
            "OBS media protocol mismatch; update both StartLive and its OBS plugin")
    if kind == 2:
        valid = not width and not height and rate == 48000 and 0 < frames <= 4800 and size == frames * 4
    else:
        valid = kind in (1, 3) and size == (8 if kind == 1 else 32) and not any(
            (stamp, width, height, rate, frames))
    if not valid:
        raise PkProtocolError("Invalid OBS media header")
    return size, (kind, stamp, width, height, rate, frames)


def read_packet(read_exact):
    size, metadata = parse_header(read_exact(HEADER.size))
    payload = read_exact(size)
    if len(payload) != size:
        raise PkProtocolError("OBS media payload is incomplete")
    if metadata[0] == 3:
        if any(value not in b"0123456789abcdef" for value in payload):
            raise PkProtocolError("Invalid OBS shared memory identifier")
        return SharedVideoSetup(payload.decode("ascii"))
    if metadata[0] == 1:
        sequence, = unpack("<Q", payload)
        if not sequence:
            raise PkProtocolError("Invalid OBS frame sequence")
        return VideoNotice(sequence)
    return MediaPacket(*metadata, payload)
