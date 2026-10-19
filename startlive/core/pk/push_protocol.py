"""PK business decoding only; authentication and ACKs belong to danmaku."""
import json

from startlive.core.constant.pk_events import OBSERVED_ONLY_COMMANDS, \
    EVENT_TYPES
from startlive.core.danmaku.protocol import DanmakuProtocol
from startlive.core.exceptions import PkProtocolError
from startlive.core.pk.events import parse_pk_event
from .trace import pk_trace


class PkPushProtocol(DanmakuProtocol):
    def begin_connection(self, key):
        packet = super().begin_connection(key)
        self._auth_request = json.loads(packet.payload)
        self._auth_request.pop("key", None)
        return packet

    def _trace_auth_response(self, packet):
        self._pk_trace("push.auth.response", packet,
                       request=getattr(self, "_auth_request", None),
                       response=self._response(packet))

    @staticmethod
    def _response(packet):
        try:
            return json.loads(packet.payload)
        except (ValueError, UnicodeDecodeError):
            return {"text": packet.payload.decode("utf-8", errors="replace"),
                    "raw_hex": packet.payload.hex()}

    def _trace_packet_failure(self, packet, error, *, request=None):
        fields = {"response": self._response(packet),
                  "error_type": type(error).__name__, "error": str(error)}
        if request is not None:
            fields.update(request={"operation": request.operation,
                                   "sequence": request.sequence,
                                   "payload": json.loads(request.payload)})
        elif packet.operation == 8:
            fields["request"] = getattr(self, "_auth_request", None)
        self._pk_trace(
            "push.send.failed" if request is not None else "push.receive.failed",
            packet, **fields)

    def _trace_sequence_ack_failure(self, sequences, error):
        pk_trace("push.sequence_ack.failed", uid=self.identity.uid,
                 room_id=self.identity.room_id,
                 queue_uuid=self.settings.queue_uuid,
                 request={"sequences": sorted(sequences)},
                 error_type=type(error).__name__, error=str(error))

    def _trace(self, event, packet, **fields):
        # Keep shared transport probes out of PK logs. Authentication results
        # still use the PK result policy and readable descriptions.
        self._pk_trace(event, packet, **fields)

    def _pk_trace(self, event, packet, **fields):
        pk_trace(event, uid=self.identity.uid, room_id=self.identity.room_id,
                 queue_uuid=self.settings.queue_uuid,
                 operation=packet.operation,
                 sequence=packet.sequence, **fields)

    def _trace_ignored_packet(self, packet, reason):
        try:
            envelope = json.loads(packet.payload)
            command = envelope.get("cmd") if isinstance(envelope,
                                                        dict) else None
            if isinstance(command,
                          str) and command in EVENT_TYPES | OBSERVED_ONLY_COMMANDS:
                self._pk_trace("push.pk.ignored", packet, command=command,
                               reason=reason, envelope=envelope)
        except Exception:
            pass

    def _message(self, packet, envelope):
        command = envelope.get("cmd")
        if isinstance(command, str) and command in OBSERVED_ONLY_COMMANDS:
            self._pk_trace("push.pk.unhandled", packet, command=command,
                           reason="native_route_unverified", envelope=envelope)
            return None
        if not isinstance(command, str) or command not in EVENT_TYPES:
            return None
        self._pk_trace("push.pk.receive", packet, command=command,
                       envelope=envelope)
        try:
            event = parse_pk_event(command, envelope)
        except PkProtocolError:
            self._pk_trace("push.pk.ignored", packet, command=command,
                           reason="invalid_pk_event")
            raise
        if event:
            self._pk_trace("push.pk.deliver", packet, command=command)
        return event
