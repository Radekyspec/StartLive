"""Cancellable TCP framing for the native business-message transport.

This layer does not decide whether a login was accepted or apply ACK/reconnect
policy. The authenticated business worker must supply those verified policies.
"""
import socket

from startlive.core.exceptions import TaskCancelled
from startlive.core.exceptions import DanmakuError, DanmakuConnectionError
from .wire import DanmakuDecoder, encode_packet, expand_packet


class DanmakuSocket:
    def __init__(self, *, cancelled=lambda: False):
        self.cancelled = cancelled
        self._socket = None
        self._decoder = DanmakuDecoder()

    def _check_cancelled(self):
        if self.cancelled():
            raise TaskCancelled()

    def connect(self, host: str, port: int, *, timeout=10):
        """Use an endpoint supplied by bootstrap; no hard-coded server address."""
        self._check_cancelled()
        if self._socket is not None:
            raise DanmakuError("业务消息连接已打开")
        self._decoder = DanmakuDecoder()
        try:
            connection = socket.create_connection((host, port), timeout=timeout)
            self._socket = connection
            connection.settimeout(0.25)
            self._check_cancelled()
        except OSError:
            self.close()
            self._check_cancelled()
            raise DanmakuConnectionError("无法连接业务消息服务器") from None
        except BaseException:
            self.close()
            raise

    def send(self, packet):
        self._check_cancelled()
        connection = self._socket
        if connection is None:
            raise DanmakuError("业务消息连接尚未打开")
        data = encode_packet(packet)
        try:
            # Sending may be slow. Never retry a partly written login or ACK.
            connection.settimeout(10)
            connection.sendall(data)
        except OSError:
            self._check_cancelled()
            raise DanmakuConnectionError("业务消息发送失败") from None
        finally:
            try:
                connection.settimeout(0.25)
            except OSError:
                pass

    def receive(self):
        """Poll complete leaf packets, retaining partial reads between calls.

        An idle poll returns an empty list so the owner can run its verified
        heartbeat/connection policy. Call send/receive from one worker thread;
        the same worker releases resources after observing cancellation.
        """
        while True:
            self._check_cancelled()
            connection = self._socket
            if connection is None:
                raise DanmakuError("业务消息连接尚未打开")
            try:
                data = connection.recv(65536)
            except socket.timeout:
                self._check_cancelled()
                return []
            except OSError:
                self._check_cancelled()
                raise DanmakuConnectionError("业务消息连接已中断") from None
            if not data:
                self._check_cancelled()
                self._decoder.finish()
                raise DanmakuConnectionError("业务消息服务器已关闭连接")
            packets = [leaf for packet in self._decoder.feed(data)
                       for leaf in expand_packet(packet)]
            return packets

    def close(self):
        connection, self._socket = self._socket, None
        if connection is not None:
            try:
                connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            connection.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
