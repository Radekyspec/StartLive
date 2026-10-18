"""Token-derived initial RTC connection confirmed by contract-2.

No initial offer HTTP endpoint: the client sets its own offer and a synthetic
remote answer, then joins over the opened binary DataChannel. This aiortc
implementation uses StartLive's own ICE policy. Direct ICE-TCP remains gated;
native local tuning is not a server requirement.
"""
import asyncio
import ipaddress
import socket
from dataclasses import replace
from threading import get_ident
from urllib.parse import urlsplit

from aiortc import (
    RTCBundlePolicy,
    RTCConfiguration,
    RTCIceServer,
    RTCPeerConnection,
    RTCSessionDescription,
)

from startlive.core.constant.pk_transport import VERIFIED_RELAY_TRANSPORTS
from startlive.core.exceptions import PkError, PkProtocolError
from startlive.core.pk.states.session import RtcTicket
from startlive.core.pk.states.transport import RtcTransportPolicy
from .rtc_diagnostics import runtime_details
from .rtc_dtls import configure_pk_dtls, observe_pk_dtls
from .rtc_relay import configure_relay, prepare_relay
from .rtc_signaling import RtcSignaling
from .rtc_users import RtcUserRegistry
from .rtc_wire import decode_ticket
from .trace import enable_dtls_failure_trace, pk_trace, sdp_for_trace


# Enable only the client-to-TURN transports demonstrated by local relay media,
# allocation failure and cancellation tests. Production PK has its own gate.


def _connection_configurations(configuration, *, relay_only):
    """aiortc uses only the first TURN URL, not the rest as fallbacks.

    Give each ticket-authorized relay path its own peer connection. Never
    turn a relay-only ticket into a direct connection while retrying.
    """
    if not relay_only:
        return [configuration]
    configurations = []
    seen = set()
    for server in configuration.iceServers:
        urls = server.urls if isinstance(server.urls, list) else [server.urls]
        for url in urls:
            if url not in seen:
                seen.add(url)
                configurations.append(replace(
                    configuration, iceServers=[replace(server, urls=[url])]))
    return configurations


def _address(value):
    try:
        parsed = urlsplit("//" + value)
        host, port = parsed.hostname, parsed.port
        if (
                not host or not port or parsed.username is not None or parsed.password is not None
                or parsed.path or parsed.query or parsed.fragment or any(
            c.isspace() for c in value)):
            raise ValueError
        return host, port
    except (ValueError, TypeError):
        raise PkProtocolError("RTC 服务器地址无效") from None


async def _resolve_addresses(addresses):
    result = []
    for address in addresses:
        host, port = _address(address)
        try:
            hosts = [str(ipaddress.ip_address(host))]
        except ValueError:
            try:
                records = await asyncio.get_running_loop().getaddrinfo(
                    host, port, type=socket.SOCK_DGRAM)
            except OSError:
                continue
            hosts = [record[4][0] for record in records]
        for value in hosts:
            if (value, port) not in result:
                result.append((value, port))
    if not result:
        raise PkError("无法解析 RTC 服务器地址")
    return result


def initial_answer(ticket, addresses):
    """Application-only answer with the native UDP candidate priorities.

    This adapter emits only the UDP subset. Native disable_udp=false also has
    passive TCP candidates; adding their text cannot implement ICE-TCP here.
    Explicit disable_udp=true is rejected before constructing a connection.
    """
    for key in ("token", "password", "fingerprint"):
        if not isinstance(ticket.get(key), str) or any(
                c in ticket[key] for c in "\r\n"):
            raise PkProtocolError("RTC 连接参数无效")
    lines = ["v=0", "o=- 0 0 IN IP4 127.0.0.1", "s=BRTC", "t=0 0",
             "a=group:BUNDLE 0", "a=msid-semantic: WMS *",
             "a=extmap-allow-mixed",
             "m=application 9 UDP/DTLS/SCTP webrtc-datachannel",
             "c=IN IP4 0.0.0.0",
             "a=ice-ufrag:" + ticket["token"],
             "a=ice-pwd:" + ticket["password"],
             "a=fingerprint:" + ticket["fingerprint"]]
    for index, (host, port) in enumerate(addresses):
        priority = 0x7EFFFFFF - (index << 8)
        lines.append(
            f"a=candidate:1 1 udp {priority} {host} {port} typ host generation 0")
    lines.extend(["a=setup:passive", "a=mid:0", "a=sctp-port:5000",
                  "a=max-message-size:262144"])
    return "\r\n".join(lines) + "\r\n"


def ice_configuration(ticket, *,
                      transport_policy: RtcTransportPolicy | None = None):
    """Enforce remote transport requirements using StartLive's local ICE policy.

    Only disable_udp changes the remote candidate protocol. Native controller
    and allocator tuning flags remain resource metadata; StartLive uses its
    maintained provider's gathering and pair selection instead. Ignoring those
    local tuning hints does not enable direct ICE-TCP or relax relay-only.
    None selects StartLive's UDP-capable default, not fetched account settings.
    """
    unsupported = []
    if transport_policy is not None:
        if not isinstance(transport_policy, RtcTransportPolicy):
            raise PkProtocolError("RTC 传输策略格式无效")
        if transport_policy.disable_udp:
            unsupported.append("仅 TCP 的远端候选")
    turn = ticket.get("turn", {})
    required_relay = bool(turn.get("turn_only"))
    transports = turn.get("transport", [])
    if required_relay:
        transports = [value for value in transports if
                      value in VERIFIED_RELAY_TRANSPORTS]
    if required_relay and not transports:
        # Unverified transport combinations cannot fall back to direct ICE.
        unsupported.append("仅通过中继连接")
    if unsupported:
        raise PkError(
            "当前 RTC 引擎尚不支持这些连接要求：" + "、".join(unsupported))
    urls = []
    for address in turn.get("addr", []):
        host, port = _address(address)
        if ":" in host:
            # aiortc 1.x TURN URI parser does not accept IPv6 literals.
            continue
        for transport in transports:
            prefix = {0: "turn", 1: "turn", 2: "turns"}.get(transport)
            if prefix:
                protocol = "udp" if transport == 0 else "tcp"
                urls.append(f"{prefix}:{host}:{port}?transport={protocol}")
    if required_relay and not urls:
        raise PkError("仅通过中继连接需要有效且受支持的 TURN 地址")
    servers = ([RTCIceServer(urls, username=turn.get("username"),
                             credential=turn.get("password"))]
               if urls else [])
    # Media RPCs omit the established application section. New media must
    # advertise the already connected transport, not fresh ports that aiortc
    # discards when applying the full, merged BUNDLE answer.
    return RTCConfiguration(iceServers=servers,
                            bundlePolicy=RTCBundlePolicy.MAX_BUNDLE)


class RtcConnection:
    # Contract37's traced colive factory instead binds
    # bilibili-rtc.dll!CreateBiliRtcEngine. Keep this adapter's identity honest.
    backend = "aiortc"

    def __init__(self, ticket: RtcTicket, *, notification=None, timeout=15,
                 leave_timeout=3, peer_connection_factory=RTCPeerConnection,
                 transport_policy: RtcTransportPolicy | None = None):
        enable_dtls_failure_trace()
        pk_trace("rtc.runtime", **runtime_details())
        pk_trace("rtc.connection.create", uid=ticket.uid,
                 channel_id=ticket.channel_id,
                 transport_policy=transport_policy, thread_id=get_ident())
        self.ticket = decode_ticket(ticket.access_token, uid=ticket.uid,
                                    channel_id=ticket.channel_id)
        self.transport_policy = transport_policy
        # Validate before allocating the PC/channels or starting ICE gathering.
        self.configuration = ice_configuration(self.ticket,
                                               transport_policy=transport_policy)
        self._relay_only = bool(self.ticket.get("turn", {}).get("turn_only"))
        self._configurations = _connection_configurations(
            self.configuration, relay_only=self._relay_only)
        self._peer_connection_factory = peer_connection_factory
        self._stage = "created"
        self.notification, self.timeout = notification, timeout
        # If no callback is injected, retain notifications received while
        # awaiting Join so the later session owner can reconcile them. The
        # bounded queue is StartLive policy, not a recovered native capacity.
        self.notifications = asyncio.Queue(maxsize=256)
        self.user_events = asyncio.Queue(maxsize=256)
        self.users = RtcUserRegistry(self._receive_user_event)
        # Bounded shutdown is StartLive policy; the native Leave timeout is
        # not established. Never hold application shutdown indefinitely.
        self.leave_timeout = leave_timeout
        self.leave_error = None
        self.join_response = None
        self.members_response = None
        self._close_task = None
        self.signaling = None
        self._create_peer(self._configurations[0])

    def _create_peer(self, configuration):
        self.configuration = configuration
        self.pc = self._peer_connection_factory(configuration)
        configure_pk_dtls(self.pc)
        if self._relay_only:
            configure_relay(self.pc)
        self.channel = self.pc.createDataChannel("sctp_data_channel_101",
                                                 id=101,
                                                 ordered=True, negotiated=False)
        self.unreliable_channel = self.pc.createDataChannel(
            "sctp_data_channel_102", id=102, ordered=False, maxRetransmits=0,
            negotiated=False)
        self._opened = asyncio.Event()
        self._dtls_start_error = None

        peer = self.pc

        def dtls_start_failed(error):
            if self.pc is peer:
                self._dtls_start_error = error
                self._opened.set()

        observe_pk_dtls(peer, dtls_start_failed)

        def on_current(emitter, event, callback):
            # A provider task may emit its final state after close() returns.
            # Retired peers must not wake or misreport the replacement peer.
            emitter.on(event, lambda: callback() if self.pc is peer else None)

        for channel in (self.channel, self.unreliable_channel):
            on_current(channel, "open", lambda channel=channel:
            self._channel_state(channel, "open"))
            on_current(channel, "close", lambda channel=channel:
            self._channel_state(channel, "close"))
        on_current(self.pc, "connectionstatechange", self._state_changed)
        dtls = getattr(getattr(self.pc, "sctp", None), "transport", None)
        if dtls is not None:
            on_current(dtls, "statechange", self._trace_dtls_state)
        for event, attribute in (
                ("iceconnectionstatechange", "iceConnectionState"),
                ("icegatheringstatechange", "iceGatheringState"),
                ("signalingstatechange", "signalingState")):
            on_current(self.pc, event, lambda attribute=attribute: self._trace(
                "rtc.pc.state", state_type=attribute,
                state=getattr(self.pc, attribute, None)))

    def _trace(self, event, **fields):
        pk_trace(event, uid=self.ticket["uid"],
                 channel_id=self.ticket["channel_id"],
                 pc_id=hex(id(self.pc)), **fields)

    def _channel_state(self, channel, event):
        self._trace("rtc.channel.state",
                    channel_label=getattr(channel, "label", None),
                    data_channel_id=getattr(channel, "id", None),
                    channel_event=event,
                    state=channel.readyState)
        if channel is self.channel:
            self._opened.set()

    def _trace_selected_pair(self):
        # Diagnostic inspection only; private provider fields never drive policy.
        try:
            connection = self.pc.sctp.transport.transport._connection
            pairs = [{side: {"type": candidate.type,
                             "transport": candidate.transport,
                             "host": candidate.host, "port": candidate.port}
                      for side, candidate in (("local", pair.local_candidate),
                                              ("remote",
                                               pair.remote_candidate))}
                     for pair in connection._nominated.values()]
            self._trace("rtc.ice.selected", pairs=pairs)
        except Exception:
            pass

    def _state_changed(self):
        self._trace("rtc.pc.state", state_type="connectionState",
                    state=self.pc.connectionState)
        if self.pc.connectionState == "failed":
            self._trace_selected_pair()
            self._trace_dtls_state()
        elif self.pc.connectionState == "connected":
            self._trace_selected_pair()
        if self.pc.connectionState in ("failed", "closed"):
            self._opened.set()

    def _trace_dtls_state(self):
        # Read-only diagnostics before close discards the handshake context.
        # Private provider fields never change validation or transport policy.
        try:
            dtls = self.pc.sctp.transport
            ssl = getattr(dtls, "_ssl", None)
            self._trace("rtc.dtls.state", thread_id=get_ident(),
                        state=getattr(dtls, "state", None),
                        encrypted=getattr(dtls, "encrypted", None),
                        ssl_state=ssl.get_state_string().decode("ascii",
                                                                errors="replace") if ssl else None,
                        cipher=ssl.get_cipher_name() if ssl else None,
                        protocol=ssl.get_protocol_version_name() if ssl else None)
        except Exception:
            pass

    def _connection_diagnostics(self):
        """Snapshot before cleanup; never include ICE/TURN credentials or SDP."""
        result = {"stage": self._stage,
                  "connection_state": getattr(self.pc, "connectionState", None),
                  "ice_state": getattr(self.pc, "iceConnectionState", None),
                  "gathering_state": getattr(self.pc, "iceGatheringState",
                                             None),
                  "channel_state": self.channel.readyState}
        try:
            sctp = self.pc.sctp
            dtls = sctp.transport
            ice = dtls.transport
            result.update(dtls_state=dtls.state, sctp_state=sctp.state)
            connection = ice._connection
            result["turn"] = {"server": connection.turn_server,
                              "transport": connection.turn_transport,
                              "tls": connection.turn_ssl}

            def candidate(value):
                return {"type": value.type, "transport": value.transport,
                        "host": value.host, "port": value.port}

            result["local_candidates"] = [
                candidate(c) for c in connection.local_candidates]
            result["pairs"] = [
                {"local": candidate(pair.local_candidate),
                 "remote": candidate(pair.remote_candidate),
                 "state": pair.state.name, "nominated": pair.nominated}
                for pair in connection._check_list]
        except (AttributeError, TypeError):
            # Diagnostics must also work with injected offline peers.
            pass
        return result

    def _receive_notification(self, message):
        handled = self.users.consume(message)
        if self.notification is not None:
            self.notification(message)
            return
        if handled:
            return
        try:
            self.notifications.put_nowait(message)
        except asyncio.QueueFull:
            self.signaling.close(
                PkError("RTC 消息处理未能跟上接收速度，连接已停止"))

    def _receive_user_event(self, event):
        try:
            self.user_events.put_nowait(event)
        except asyncio.QueueFull:
            error = PkError("RTC 成员消息处理未能跟上接收速度")
            self.signaling.close(error)
            raise error from None

    async def __aenter__(self):
        self._trace("rtc.connection.start", timeout=self.timeout)
        try:
            await asyncio.wait_for(self._connect(), self.timeout)
            self._trace("rtc.connection.ready",
                        callid=self.join_response.get("callid", 0))
            self._trace_selected_pair()
            return self
        except asyncio.TimeoutError:
            self._trace("rtc.connection.timeout", timeout=self.timeout,
                        **self._connection_diagnostics())
            await self.close()
            raise PkError("RTC 初始连接超时") from None
        except BaseException as error:
            self._trace("rtc.connection.failed", error=error,
                        **self._connection_diagnostics())
            await self.close()
            raise

    async def _connect(self):
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.timeout
        self._stage = "resolving"
        addresses = await _resolve_addresses(self.ticket["addr"])
        self._trace("rtc.connection.resolved", addresses=addresses)
        for index, configuration in enumerate(self._configurations):
            remaining = deadline - loop.time()
            if remaining <= 0:
                raise asyncio.TimeoutError
            if index:
                self._create_peer(configuration)
            # Reserve time for the other advertised paths instead of letting
            # a blackholed UDP path consume the entire connection deadline.
            attempt_timeout = remaining / (len(self._configurations) - index)
            try:
                await asyncio.wait_for(self._open_transport(addresses),
                                       attempt_timeout)
                break
            except (asyncio.TimeoutError, PkError, OSError) as error:
                dtls = getattr(getattr(self.pc, "sctp", None), "transport",
                               None)
                if (index + 1 == len(self._configurations)
                        or isinstance(error, PkProtocolError)
                        or self._dtls_start_error is not None
                        or getattr(dtls, "state", None) == "failed"):
                    raise
                next_configuration = self._configurations[index + 1]
                self._trace("rtc.connection.retry", attempt=index + 1,
                            error_type=type(error).__name__,
                            next_turn_url=next_configuration.iceServers[0].urls[
                                0],
                            **self._connection_diagnostics())
                # Retire all sockets, TURN allocations and callbacks before
                # replacing the PC. Cancellation must not start another peer.
                await self.pc.close()
        # Retry only transport establishment. Once Join can have been sent,
        # replaying it on a fresh peer could create a duplicate server session.
        self._trace_dtls_state()
        self.signaling = RtcSignaling(self.channel, self.ticket,
                                      notification=self._receive_notification)
        self._stage = "join"
        with self.signaling.block_notifications():
            self.join_response = await self.signaling.join()
            self._stage = "members"
            with self.signaling.block_notifications():
                self.members_response = await self.signaling.refresh_members(
                    self.join_response.get("callid", 0))
                self.users.initialize(self.members_response.get("users", []))
        if self.signaling.closed:
            raise PkError("RTC 初始成员信息同步失败")
        self._stage = "ready"

    async def _open_transport(self, addresses):
        self._stage = "gathering"
        prepare_relay(self.pc)
        offer = await self.pc.createOffer()
        self._trace("rtc.sdp.local.offer", stage="initial",
                    sdp=sdp_for_trace(offer.sdp))
        await self.pc.setLocalDescription(offer)
        self._trace("rtc.ice.gathered", **self._connection_diagnostics())
        self._trace("rtc.sdp.local.applied", stage="initial",
                    sdp=sdp_for_trace(self.pc.localDescription.sdp))
        answer = initial_answer(self.ticket, addresses)
        self._trace("rtc.sdp.remote.answer", stage="initial",
                    sdp=sdp_for_trace(answer))
        self._stage = "remote_description"
        await self.pc.setRemoteDescription(
            RTCSessionDescription(answer, "answer"))
        self._trace("rtc.sdp.remote.applied", stage="initial",
                    sdp=sdp_for_trace(self.pc.remoteDescription.sdp))
        self._stage = "transport"
        await self._opened.wait()
        if self._dtls_start_error is not None:
            raise PkError(
                "RTC 安全连接启动失败（DTLS），详细原因已记录到日志") from self._dtls_start_error
        if self.channel.readyState != "open":
            dtls = getattr(getattr(self.pc, "sctp", None), "transport", None)
            if getattr(dtls, "state", None) == "failed":
                raise PkError("RTC 安全握手失败（DTLS），详细原因已记录到日志")
            raise PkError("RTC 信令连接失败")

    async def __aexit__(self, exc_type, *_):
        await self.close()
        if exc_type is None and self.leave_error is not None:
            raise self.leave_error

    async def close(self):
        if self._close_task is None:
            self._close_task = asyncio.create_task(self._close())
        await asyncio.shield(self._close_task)

    async def _close(self):
        self._trace("rtc.connection.close.start",
                    joined=bool(self.signaling and self.signaling.joined))
        try:
            if self.signaling and self.signaling.joined and not self.signaling.closed:
                try:
                    await asyncio.wait_for(self.signaling.leave(),
                                           self.leave_timeout)
                except asyncio.TimeoutError:
                    self.leave_error = PkError(
                        "RTC 退会请求超时，已关闭本地连接")
                    self._trace("rtc.leave.timeout", timeout=self.leave_timeout)
                except Exception as error:
                    self.leave_error = error
                    self._trace("rtc.leave.failed", error=error)
        finally:
            # Native completion cleans up on both success and failure.
            if self.signaling:
                self.signaling.close()
            await self.pc.close()
            self.users.clear()
            self._trace("rtc.connection.closed", leave_error=self.leave_error)
