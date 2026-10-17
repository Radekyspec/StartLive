"""Verified authentication, duplicate filtering and both ACK paths.

StartLive requires code0 before delivering events, unlike the permissive native
auth consumer. The separate sequence ACK callback submits an HTTP request.
Sequence and msg_id caches belong to the context, not an individual socket.
"""
from collections import OrderedDict
from contextlib import contextmanager
import json

from startlive.core.exceptions import DanmakuAuthenticationError, \
    DanmakuProtocolError, DanmakuTokenExpired
from .trace import danmaku_trace
from .wire import login_packet
from startlive.core.danmaku.states.models import DanmakuPacket, DanmakuMessage


def _object(payload):
    try:
        value = json.loads(payload)
    except (ValueError, UnicodeDecodeError):
        raise DanmakuProtocolError("业务推送返回了无效 JSON") from None
    if not isinstance(value, dict):
        raise DanmakuProtocolError("业务推送内容不是 JSON 对象")
    return value


class DanmakuProtocol:
    def __init__(self, identity, settings, *, sequence_ack,
                 message_cache_size=2000):
        if not callable(sequence_ack):
            raise DanmakuProtocolError("尚未配置业务推送序列确认接口")
        if type(message_cache_size) is not int or not -(
                1 << 31) <= message_cache_size < 1 << 31:
            raise DanmakuProtocolError("业务推送缓存长度无效")
        self.identity, self.settings = identity, settings
        self.sequence_ack = sequence_ack
        self.message_cache_size = message_cache_size
        self._message_ids, self._sequences = OrderedDict(), set()
        self._observed_commands, self._observed_operations = set(), set()
        self.authenticated = False
        self.next_sequence = 1

    def begin_connection(self, key):
        """Fresh socket counter, same queue UUID and context dedupe caches."""
        self.authenticated = False
        self.next_sequence = 2
        self._observed_commands.clear()
        self._observed_operations.clear()
        packet = login_packet(self.identity, self.settings, key=key, sequence=1)
        self._trace("push.auth.send", packet,
                    buvid_present=bool(self.settings.buvid),
                    buvid_source="cookie_buvid3",
                    buvid_matches_cookie=self.settings.buvid == dict(
                        self.identity.cookies).get("buvid3", ""),
                    http_buvid_matches_push=self.settings.buvid == self.identity.buvid,
                    auth_mode="access_key" if self.identity.access_key else "cookie")
        return packet

    def _trace(self, event, packet, **fields):
        danmaku_trace(event, uid=self.identity.uid,
                      room_id=self.identity.room_id,
                      queue_uuid=self.settings.queue_uuid,
                      operation=packet.operation,
                      sequence=packet.sequence, **fields)

    def _trace_auth_response(self, packet):
        try:
            payload = json.loads(packet.payload)
        except (ValueError, UnicodeDecodeError):
            payload = packet.payload
        self._trace("push.auth.response", packet,
                    code=payload.get("code") if isinstance(payload,
                                                           dict) else None)

    def _trace_command(self, packet, command):
        # A missing JOIN must be distinguishable from an unhandled command.
        # Record names once per socket, bounded; never dump unrelated messages.
        if (not isinstance(command, str) or not 0 < len(command) <= 96
                or not all(
                    c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_:" for c in
                    command)
                or command in self._observed_commands or len(
                    self._observed_commands) >= 64):
            return
        self._observed_commands.add(command)
        self._trace("push.command.observed", packet, command=command)

    def _trace_ignored_packet(self, packet, reason):
        self._trace("push.message.ignored", packet, reason=reason)

    def _message(self, packet, envelope):
        """Domain adapters may decode accepted envelopes on the worker."""
        command = envelope.get("cmd")
        return DanmakuMessage(command if isinstance(command, str) else "",
                              packet.sequence, envelope)

    @contextmanager
    def _processing(self, packet):
        try:
            yield
        except Exception as error:
            self._trace_packet_failure(packet, error)
            raise

    def _trace_packet_failure(self, packet, error, *, request=None):
        self._trace("push.receive.failed", packet,
                    error_type=type(error).__name__, error=str(error))

    def _send_ack(self, request, response, send):
        try:
            send(request)
        except Exception as error:
            self._trace_packet_failure(response, error, request=request)
            raise

    def _trace_sequence_ack_failure(self, sequences, error):
        danmaku_trace("push.sequence_ack.failed", uid=self.identity.uid,
                      room_id=self.identity.room_id,
                      queue_uuid=self.settings.queue_uuid,
                      request={"sequences": sorted(sequences)},
                      error_type=type(error).__name__, error=str(error))

    def _outgoing(self, operation, payload):
        packet = DanmakuPacket(1, operation, self.next_sequence, payload)
        self.next_sequence = (self.next_sequence + 1) & 0xFFFFFFFF
        return packet

    def heartbeat(self):
        # secret37430 -> 3ab40(counter,2) -> 3adf0 builds only the16-byte
        # version1 header, then37430 sends that vector without appending a body.
        return self._outgoing(2, b"")

    def _remember_message(self, message_id):
        duplicate = message_id in self._message_ids
        self._message_ids.pop(message_id, None)
        self._message_ids[message_id] = None
        # Native refreshes recency even for duplicates, then removes exactly
        # one first entry when size >= unsigned(sign-extended signed32 config).
        threshold = self.message_cache_size & 0xFFFFFFFFFFFFFFFF
        if len(self._message_ids) >= threshold:
            self._message_ids.popitem(last=False)
        return not duplicate

    def _authenticate(self, packet):
        self.authenticated = False
        self._trace_auth_response(packet)
        code = _object(packet.payload).get("code")
        if type(code) is not int:
            raise DanmakuProtocolError("业务推送鉴权响应缺少有效的 code")
        if code == -101:
            self.authenticated = False
            raise DanmakuTokenExpired("业务推送令牌已过期，需要重新获取连接信息")
        if code != 0:
            self.authenticated = False
            raise DanmakuAuthenticationError(f"业务推送鉴权失败（错误码 {code}）")
        self.authenticated = True

    def receive(self, packets, *, send):
        """Handle expanded packets; send acknowledgements before event delivery."""
        business, sequences = [], set()
        for packet in packets:
            with self._processing(packet):
                if packet.operation == 8:
                    self._authenticate(packet)
                elif packet.operation == 5:
                    if not self.authenticated:
                        self._trace_ignored_packet(packet, "not_authenticated")
                        raise DanmakuAuthenticationError("业务推送尚未完成鉴权")
                    if packet.sequence:
                        sequences.add(packet.sequence)
                        if packet.sequence in self._sequences:
                            self._trace_ignored_packet(packet,
                                                       "duplicate_sequence")
                            continue
                        self._sequences.add(packet.sequence)
                    business.append(packet)
                elif packet.operation not in (
                        3,) and packet.operation not in self._observed_operations:
                    if len(self._observed_operations) < 16:
                        self._observed_operations.add(packet.operation)
                        self._trace("push.operation.unhandled", packet,
                                    payload_bytes=len(packet.payload))
        if sequences:
            try:
                self.sequence_ack(tuple(sorted(sequences)))
            except Exception as error:
                self._trace_sequence_ack_failure(sequences, error)
                raise
        events = []
        for packet in business:
            with self._processing(packet):
                envelope = _object(packet.payload)
                command = envelope.get("cmd")
                self._trace_command(packet, command)
                if self.settings.support_ack:
                    message_id = envelope.get("msg_id")
                    message_id = message_id if isinstance(message_id,
                                                          str) else ""
                    command = envelope.get("cmd")
                    command = command if isinstance(command, str) else ""
                    message_type = envelope.get("p_msg_type")
                    if type(message_type) is not int or not -(
                            1 << 63) <= message_type < 1 << 63:
                        message_type = 0
                    if envelope.get("p_is_ack") is True:
                        body = json.dumps({"msg_id": message_id, "cmd": command,
                                           "p_msg_type": message_type},
                                          ensure_ascii=False,
                                          separators=(",", ":")).encode("utf-8")
                        self._send_ack(self._outgoing(24, body), packet, send)
                    if message_type == 1 and not self._remember_message(
                            message_id):
                        self._trace_ignored_packet(packet,
                                                   "duplicate_message_id")
                        continue
                event = self._message(packet, envelope)
                if event is not None:
                    events.append(event)
        return events
