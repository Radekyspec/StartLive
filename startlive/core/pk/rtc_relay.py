"""Scoped, fail-closed TURN gathering for the reviewed aiortc/aioice versions.

The original ICE Connection and its bound send/recv methods stay in place.
Only explicitly configured PCs use this adapter; it does not enable a transport
capability or change token parsing, SDP, signaling or the dependency versions.
"""
import asyncio
import socket
from importlib.metadata import version

from aioice import stun, turn
from aioice.candidate import Candidate, candidate_foundation, candidate_priority
from aioice.ice import Connection, StunProtocol, TransportPolicy

from startlive.core.exceptions import PkError
from .trace import pk_trace


def _unsupported():
    return PkError("当前 RTC 库不支持所需的仅中继连接")


async def _drain_close(task):
    # A cancelled owner must not report its resources gone while shielded
    # cleanup is still running. Preserve cancellation after actual retirement.
    cancelled = None
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError as error:
            cancelled = error
    result = task.result()
    if cancelled is not None:
        raise cancelled
    return result


async def _create_endpoint(inner, connection):
    """Use the library's TURN protocol/auth, with explicit endpoint ownership."""
    loop = asyncio.get_running_loop()
    if connection.turn_transport == "tcp":
        transport, _ = await loop.create_connection(
            lambda: inner, host=connection.turn_server[0],
            port=connection.turn_server[1], ssl=connection.turn_ssl)
    else:
        transport, _ = await loop.create_datagram_endpoint(
            lambda: inner, remote_addr=connection.turn_server)
        # Keep aioice.create_turn_endpoint's receive-buffer policy. A custom
        # endpoint without this setting drops video bursts before Python sees
        # them (Windows defaults to 64 KiB), including audio/control traffic.
        try:
            sock = transport.get_extra_info("socket")
            if sock is not None:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF,
                                turn.UDP_SOCKET_BUFFER_SIZE)
                pk_trace("rtc.relay.receive_buffer",
                         bytes=sock.getsockopt(socket.SOL_SOCKET,
                                               socket.SO_RCVBUF))
        except BaseException:
            transport.close()
            raise
    return transport


class _RelayTransport(turn.TurnTransport):
    def __init__(self, allocation):
        super().__init__(allocation.inner)
        self.allocation = allocation

    def sendto(self, data, addr):
        self.allocation.send(data, addr)

    def close(self):
        self.allocation.begin_close()


class _Allocation:
    def __init__(self, adapter, component):
        self.adapter, self.component = adapter, component
        connection = adapter.connection
        protocol_class = (
            turn.TurnClientTcpProtocol if connection.turn_transport == "tcp"
            else turn.TurnClientUdpProtocol)
        self.inner = protocol_class(connection.turn_server,
                                    username=connection.turn_username,
                                    password=connection.turn_password,
                                    lifetime=turn.DEFAULT_ALLOCATION_LIFETIME,
                                    channel_refresh_time=turn.DEFAULT_CHANNEL_REFRESH_TIME)
        self.endpoint_closed = asyncio.Event()
        original_lost = self.inner.connection_lost

        def connection_lost(error):
            try:
                original_lost(error)
            finally:
                self.endpoint_closed.set()

        self.inner.connection_lost = connection_lost
        self.raw = self.protocol = None
        self.tasks = set()
        self.close_task = None
        self.closing = False

    async def open(self):
        stage = "endpoint"
        try:
            # inner exists before endpoint creation, so even cancellation after
            # connection_made but before this await returns has an owned socket.
            self.raw = await self.adapter.owner.endpoint_factory(self.inner,
                                                                 self.adapter.connection)
            self.protocol = StunProtocol(self.adapter.connection)
            transport = _RelayTransport(self)
            stage = "allocate"
            await transport._connect(self.protocol)
            stage = "candidate"
            address = transport.get_extra_info("sockname")
            related = transport.get_extra_info("related_address")
            candidate = Candidate(
                foundation=candidate_foundation("relay", "udp", address[0]),
                component=self.component, transport="udp",
                priority=candidate_priority(self.component, "relay"),
                host=address[0], port=address[1], type="relay",
                related_address=related[0], related_port=related[1])
            self.protocol.local_candidate = candidate
            pk_trace("rtc.relay.allocated", component=self.component,
                     server=self.adapter.connection.turn_server,
                     transport=self.adapter.connection.turn_transport,
                     tls=bool(self.adapter.connection.turn_ssl),
                     relay_address=address)
            return candidate, self.protocol
        except BaseException as error:
            if not isinstance(error, asyncio.CancelledError):
                connection = self.adapter.connection
                detail = str(error)
                for credential in (connection.turn_username,
                                   connection.turn_password):
                    if credential:
                        detail = detail.replace(credential, "[redacted]")
                code = (error.response.attributes.get("ERROR-CODE", (None,))[0]
                        if isinstance(error, stun.TransactionFailed) else None)
                pk_trace("rtc.relay.allocate.failed", stage=stage,
                         component=self.component,
                         server=connection.turn_server,
                         transport=connection.turn_transport,
                         tls=bool(connection.turn_ssl),
                         error_type=type(error).__name__,
                         error=detail, stun_code=code)
            await self.close(force=True)
            raise

    def send(self, data, addr):
        if self.closing:
            return
        task = asyncio.create_task(self.inner.send_data(data, addr))
        self.tasks.add(task)
        task.add_done_callback(self._sent)

    def _sent(self, task):
        self.tasks.discard(task)
        if not task.cancelled() and task.exception() is not None:
            pk_trace("rtc.relay.send.failed",
                     error_type=type(task.exception()).__name__,
                     error=task.exception())
            self.begin_close(force=True)

    def begin_close(self, *, force=False):
        if self.close_task is None:
            self.closing = True
            self.close_task = asyncio.create_task(self._close(force))
        return self.close_task

    async def close(self, *, force=False):
        await _drain_close(self.begin_close(force=force))

    async def _close(self, force):
        tasks = list(self.tasks)
        refresh = self.inner.refresh_task
        if refresh is not None:
            tasks.append(refresh)
            self.inner.refresh_task = None
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raw = self.raw or getattr(self.inner, "transport", None)
        abort = force
        try:
            if not force and raw is not None and self.inner.relayed_address is not None:
                try:
                    await asyncio.wait_for(self.inner.delete(),
                                           self.adapter.owner.close_timeout)
                except (Exception, asyncio.CancelledError):
                    # Forced local close is still required when the relay does
                    # not acknowledge deletion. Never leave its refresh alive.
                    abort = True
        finally:
            if raw is not None:
                if abort:
                    raw.abort()
                else:
                    raw.close()
                try:
                    await asyncio.wait_for(self.endpoint_closed.wait(),
                                           self.adapter.owner.close_timeout)
                except asyncio.TimeoutError:
                    # TLS close() may await a peer shutdown. Bound that wait,
                    # force the underlying transport closed, then drain its
                    # connection_lost callback before releasing ownership.
                    raw.abort()
                    try:
                        await asyncio.wait_for(self.endpoint_closed.wait(),
                                               self.adapter.owner.close_timeout)
                    except asyncio.TimeoutError:
                        raise PkError("关闭 TURN 中继连接超时") from None


class _RelayConnection:
    def __init__(self, owner, ice):
        self.owner, self.ice = owner, ice
        self.gatherer, self.connection = ice.iceGatherer, ice.iceGatherer._connection
        connection = self.connection
        self.original_close = connection.close
        self.allocations = []
        self.gather_task = self.close_task = None
        self.closing = self.failed = False
        connection._use_ipv4 = connection._use_ipv6 = False
        connection.stun_server = None
        connection._transport_policy = TransportPolicy.RELAY
        connection.gather_candidates = self.gather
        connection.close = self.close

    def validate(self, *, complete=False):
        connection = self.connection
        if (
                self.ice._connection is not connection or self.gatherer._connection is not connection
                or getattr(self.ice._recv, "__self__", None) is not connection
                or getattr(self.ice._send, "__self__", None) is not connection
                or connection.gather_candidates != self.gather or connection.close != self.close
                or self.closing or self.failed):
            raise _unsupported()
        candidates = connection._local_candidates
        protocols = connection._protocols
        if any(c.type != "relay" or c.transport != "udp" for c in candidates):
            raise _unsupported()
        admitted = {allocation.protocol for allocation in self.allocations if
                    allocation.protocol}
        if any(p not in admitted or p.local_candidate not in candidates for p in
               protocols):
            raise _unsupported()
        pairs = list(connection._check_list) + list(
            connection._nominated.values())
        if (any(
                pair.protocol not in protocols or pair.local_candidate.type != "relay"
                for pair in pairs)
                or any(item[2] not in protocols for item in
                       connection._early_checks)):
            raise _unsupported()
        if complete and (not candidates or not protocols
                         or {c.component for c in
                             candidates} != connection._components):
            raise PkError("TURN 未分配可用的中继连接")

    async def gather(self):
        self.validate(complete=self.connection._local_candidates_end)
        if self.gather_task is None:
            self.gather_task = asyncio.create_task(self._gather())
        await self.gather_task

    async def _gather(self):
        connection = self.connection
        connection._local_candidates_start = True
        try:
            for component in sorted(connection._components):
                allocation = _Allocation(self, component)
                self.allocations.append(allocation)
                candidate, protocol = await asyncio.wait_for(
                    allocation.open(), self.owner.allocation_timeout)
                # No await between allocation handoff and registering both
                # objects. Cancellation still finds allocation in our list.
                connection._protocols.append(protocol)
                connection._local_candidates.append(candidate)
            self.validate(complete=True)
            connection._local_candidates_end = True
        except BaseException as error:
            self.failed = True
            await asyncio.gather(
                *(a.close(force=True) for a in self.allocations))
            if isinstance(error, (asyncio.CancelledError, PkError)):
                raise
            if isinstance(error, asyncio.TimeoutError):
                raise PkError("TURN 中继连接分配超时") from error
            raise PkError("TURN 中继连接分配失败") from error

    async def close(self):
        if self.close_task is None:
            self.closing = True
            self.close_task = asyncio.create_task(self._close())
        await _drain_close(self.close_task)

    async def _close(self):
        try:
            if self.gather_task is not None and not self.gather_task.done():
                self.gather_task.cancel()
                await asyncio.gather(self.gather_task, return_exceptions=True)
            await asyncio.gather(
                *(a.close(force=self.failed) for a in self.allocations))
            await self.original_close()
        finally:
            self.owner.adapters.pop(self.connection, None)


class _RelayOwner:
    def __init__(self, pc, allocation_timeout, close_timeout, endpoint_factory):
        self.pc = pc
        self.allocation_timeout, self.close_timeout = allocation_timeout, close_timeout
        self.endpoint_factory = endpoint_factory or _create_endpoint
        self.adapters = {}
        self.original_close = pc.close
        self.close_task = None
        pc.close = self.close

    @property
    def connections(self):
        return tuple(self.adapters)

    async def close(self):
        if self.close_task is None:
            self.close_task = asyncio.create_task(self._close())
        await _drain_close(self.close_task)

    async def _close(self):
        try:
            await self.original_close()
        finally:
            await asyncio.gather(
                *(a.close() for a in tuple(self.adapters.values())))
            self.adapters.clear()


def configure_relay(pc, *, allocation_timeout=5, close_timeout=3,
                    endpoint_factory=None):
    """Mark one PC for relay preparation; this never starts an allocation."""
    existing = getattr(pc, "_startlive_relay_owner", None)
    if existing is not None:
        return existing
    if version("aiortc") != "1.15.0" or version("aioice") != "0.10.2":
        raise _unsupported()
    owner = _RelayOwner(pc, allocation_timeout, close_timeout, endpoint_factory)
    pc._startlive_relay_owner = owner
    return owner


def prepare_relay(pc):
    """Prepare all actual current gatherers before each local offer/gather."""
    owner = getattr(pc, "_startlive_relay_owner", None)
    if owner is None:
        return
    try:
        if owner.close_task is not None:
            raise _unsupported()
        transports = {t.receiver.transport.transport for t in
                      pc.getTransceivers()}
        if pc.sctp is not None:
            transports.add(pc.sctp.transport.transport)
        # Fail explicitly if a changed library retains an unexamined transport.
        if transports != pc._RTCPeerConnection__iceTransports:
            raise _unsupported()
        for ice in transports:
            gatherer, connection = ice.iceGatherer, ice.iceGatherer._connection
            existing = owner.adapters.get(connection)
            if existing is not None:
                existing.validate(complete=connection._local_candidates_end)
                continue
            if (not isinstance(connection,
                               Connection) or gatherer.state != "new"
                    or connection._closed or connection._local_candidates_start
                    or connection._local_candidates_end or connection._local_candidates
                    or connection._protocols or connection._check_list
                    or connection._early_checks or connection._nominated
                    or not connection._components or not connection.turn_server
                    or connection.turn_transport not in ("udp", "tcp")
                    or (
                            connection.turn_ssl and connection.turn_transport != "tcp")
                    or ice._connection is not connection
                    or getattr(ice._recv, "__self__", None) is not connection
                    or getattr(ice._send, "__self__", None) is not connection):
                raise _unsupported()
            adapter = _RelayConnection(owner, ice)
            owner.adapters[connection] = adapter
    except (AttributeError, TypeError, KeyError) as error:
        raise _unsupported() from error
