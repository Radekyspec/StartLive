"""Blocking connection loop; run only in a pool worker.

Reconnect keeps the dedupe context; token refresh replaces it. HTTP sequence
ACKs are enqueued to a different worker. Only this loop touches/closes sockets.
"""
from dataclasses import replace
import json
from time import monotonic
from uuid import uuid4

from startlive.core.exceptions import (
    DanmakuError,
    DanmakuAuthenticationError,
    DanmakuProtocolError,
    DanmakuConnectionError,
    DanmakuTokenExpired,
)
from .identity import require_current_identity
from .protocol import DanmakuProtocol
from .socket import DanmakuSocket
from .trace import danmaku_trace
from startlive.core.constant.danmaku_wire import HEARTBEAT_INTERVAL_SECONDS
from startlive.core.constant.danmaku import DanmakuState


class DanmakuClient:
    def __init__(self, identity, *, settings, sequence_ack, bootstrap,
                 cancellation,
                 transport_factory=DanmakuSocket,
                 protocol_factory=DanmakuProtocol,
                 identity_guard=require_current_identity, clock=monotonic,
                 auth_timeout=15,
                 receive_timeout=HEARTBEAT_INTERVAL_SECONDS * 3):
        # Three silent heartbeat intervals are a local liveness policy.
        if auth_timeout <= 0 or receive_timeout <= HEARTBEAT_INTERVAL_SECONDS:
            raise ValueError("Invalid danmaku timeout")
        self.identity, self.settings = identity, settings
        self.sequence_ack, self.bootstrap = sequence_ack, bootstrap
        self.cancellation, self.identity_guard = cancellation, identity_guard
        self.transport_factory, self.protocol_factory = transport_factory, protocol_factory
        self.clock, self.auth_timeout, self.receive_timeout = clock, auth_timeout, receive_timeout
        self._transport = None

    def _check_identity(self):
        self.cancellation.raise_if_cancelled()
        self.identity_guard(self.identity)

    def _trace_failure(self, event, error, bootstrap, settings, stage, packet):
        request = None
        if packet is not None:
            payload = json.loads(packet.payload) if packet.payload else {}
            payload.pop("key", None)
            request = {"operation": packet.operation,
                       "sequence": packet.sequence, "payload": payload}
        danmaku_trace(event, uid=self.identity.uid,
                      room_id=self.identity.room_id,
                      queue_uuid=settings.queue_uuid, host=bootstrap.host,
                      port=bootstrap.port,
                      stage=stage, request=request,
                      response=getattr(error, "response", None),
                      error_type=type(error).__name__, reason=str(error))

    def run(self, report_progress, *args, **kwargs):
        def report(value):
            if isinstance(value, DanmakuState):
                danmaku_trace("connection.state", uid=self.identity.uid,
                              room_id=self.identity.room_id, state=value.value)
            if report_progress:
                report_progress(value)

        bootstrap, protocol = None, None
        settings = self.settings
        while True:
            self._check_identity()
            if bootstrap is None:
                bootstrap = self.bootstrap(self.identity)
                self._check_identity()
                if not bootstrap.key or not bootstrap.host or not 0 < bootstrap.port <= 65535:
                    raise DanmakuProtocolError("业务推送连接信息不完整")
                protocol = self.protocol_factory(self.identity, settings,
                                                 sequence_ack=lambda values:
                                                 self.sequence_ack(
                                                     self.identity,
                                                     settings.queue_uuid,
                                                     values))
            transport = self.transport_factory(
                cancelled=lambda: bool(self.cancellation))
            self._transport = transport
            reconnect = False
            stage, request = "connect", None
            try:
                report(DanmakuState.CONNECTING)
                transport.connect(bootstrap.host, bootstrap.port)
                request = login = protocol.begin_connection(bootstrap.key)
                stage = "send"
                transport.send(request)
                started = self.clock()
                last_heartbeat = started - HEARTBEAT_INTERVAL_SECONDS
                last_received = started
                while True:
                    self._check_identity()
                    now = self.clock()
                    if now - last_heartbeat >= HEARTBEAT_INTERVAL_SECONDS:
                        stage, request = "send", protocol.heartbeat()
                        transport.send(request)
                        last_heartbeat = now
                    was_authenticated = protocol.authenticated
                    stage, request = "receive", login if not was_authenticated else None
                    packets = transport.receive()
                    if packets:
                        last_received = self.clock()
                    stage, request = "process", None
                    events = protocol.receive(packets, send=transport.send)
                    if protocol.authenticated and not was_authenticated:
                        report(DanmakuState.AUTHENTICATED)
                    for event in events:
                        self._check_identity()
                        report(event)
                    self._check_identity()
                    now = self.clock()
                    if protocol.authenticated and now - last_received >= self.receive_timeout:
                        stage, request = "heartbeat_timeout", None
                        raise DanmakuConnectionError(
                            "弹幕连接长时间未收到数据或心跳回应")
                    if not protocol.authenticated and now - started >= self.auth_timeout:
                        stage, request = "auth_timeout", login
                        raise DanmakuAuthenticationError("等待业务推送鉴权超时")
            except DanmakuTokenExpired:
                # Stop/Start recreates context; ordinary reconnect below does not.
                bootstrap, protocol = None, None
                settings = replace(settings, queue_uuid=str(uuid4()))
                report(DanmakuState.REFRESHING_TOKEN)
            except DanmakuConnectionError as error:
                self._check_identity()
                self._trace_failure("connection.reconnect", error, bootstrap,
                                    settings, stage, request)
                reconnect = True
                report(DanmakuState.RECONNECTING)
            except DanmakuError as error:
                self._trace_failure("connection.failed", error, bootstrap,
                                    settings, stage, request)
                raise
            finally:
                transport.close()
                self._transport = None
            if reconnect:
                self.cancellation.wait(1)
