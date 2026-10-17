"""Verified Goim login, framing and compressed packet expansion.

Authentication, ACKs and connection lifetime belong to protocol and client.
"""
import json
import zlib

import brotli

from startlive.core.constant.danmaku_wire import HEADER, MAX_PACKET_BYTES
from startlive.core.danmaku.states.models import DanmakuIdentity, \
    DanmakuLoginSettings, DanmakuPacket
from startlive.core.exceptions import DanmakuProtocolError


def login_packet(identity: DanmakuIdentity, settings: DanmakuLoginSettings, *,
                 key: str,
                 sequence: int) -> DanmakuPacket:
    if type(settings.support_ack) is not bool:
        raise DanmakuProtocolError(
            "推送登录的 support_ack 必须明确指定为布尔值")
    payload = {
        "roomid": identity.room_id, "uid": identity.uid, "key": key,
        "protover": 3, "app_id": 102, "build": settings.build,
        "buvid": settings.buvid, "mobi_app": "pc_link", "platform": "pc_link",
        "channel": "bili", "version_name": settings.version_name,
        "device": settings.device, "osver": settings.osver,
        "support_ack": settings.support_ack, "queue_uuid": settings.queue_uuid,
    }
    return DanmakuPacket(1, 7, sequence,
                         json.dumps(payload, ensure_ascii=False,
                                    separators=(",", ":")).encode("utf-8"))


def encode_packet(packet: DanmakuPacket) -> bytes:
    size = HEADER.size + len(packet.payload)
    if size > MAX_PACKET_BYTES:
        raise DanmakuProtocolError("推送报文过大")
    return HEADER.pack(size, HEADER.size, packet.version, packet.operation,
                       packet.sequence) + packet.payload


class DanmakuDecoder:
    """Incrementally split raw TCP reads; retain version and uninterpreted body."""

    def __init__(self):
        self._buffer = bytearray()

    def feed(self, data: bytes) -> list[DanmakuPacket]:
        self._buffer.extend(data)
        result, offset = [], 0
        while len(self._buffer) - offset >= HEADER.size:
            size, header_size, version, operation, sequence = HEADER.unpack_from(
                self._buffer, offset)
            if not HEADER.size <= header_size <= size <= MAX_PACKET_BYTES:
                response = {"raw_hex": self._buffer[offset:].hex()}
                self._buffer.clear()
                raise DanmakuProtocolError("推送报文头无效", response=response)
            if len(self._buffer) - offset < size:
                break
            result.append(DanmakuPacket(version, operation, sequence,
                                        bytes(self._buffer[
                                                  offset + header_size:offset + size])))
            offset += size
        del self._buffer[:offset]
        return result

    def finish(self):
        if self._buffer:
            raise DanmakuProtocolError("推送数据在完整报文接收前结束",
                                       response={"raw_hex": self._buffer.hex()})


def expand_packet(packet: DanmakuPacket, *, _depth=0) -> list[DanmakuPacket]:
    try:
        return _expand_packet(packet, _depth=_depth)
    except DanmakuProtocolError as error:
        if error.response is None:
            error.response = {"version": packet.version,
                              "operation": packet.operation,
                              "sequence": packet.sequence,
                              "raw_hex": packet.payload.hex()}
        raise


def _expand_packet(packet: DanmakuPacket, *, _depth=0) -> list[DanmakuPacket]:
    """Version 2 is zlib, 3 is Brotli; output is nested packets, not JSON."""
    if packet.version not in (2, 3):
        return [packet]
    if _depth >= 8:
        raise DanmakuProtocolError("推送报文嵌套过深")
    try:
        if packet.version == 2:
            decoder = zlib.decompressobj()
            payload = decoder.decompress(packet.payload, MAX_PACKET_BYTES + 1)
            complete = decoder.eof and not decoder.unused_data
        else:
            decoder = brotli.Decompressor()
            payload = decoder.process(packet.payload,
                                      output_buffer_limit=MAX_PACKET_BYTES + 1)
            complete = decoder.is_finished()
    except (zlib.error, brotli.error):
        raise DanmakuProtocolError("推送压缩报文无效") from None
    if len(payload) > MAX_PACKET_BYTES or not complete:
        raise DanmakuProtocolError("推送压缩报文过大或不完整")
    parser = DanmakuDecoder()
    packets = parser.feed(payload)
    parser.finish()
    return [leaf for inner in packets for leaf in
            expand_packet(inner, _depth=_depth + 1)]
