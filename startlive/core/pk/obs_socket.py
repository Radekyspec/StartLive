"""Cancellable local media socket for Linux and macOS; StartLive files only."""
import errno
import os
import socket
import stat
from pathlib import Path
from time import monotonic, sleep

from startlive.core.exceptions import PkError
from startlive.core.exceptions import TaskCancelled


def local_media_path():
    # Shared with the OBS plugin. A private UID directory keeps the socket
    # local to this user, independent of OBS/terminal TMPDIR differences.
    return Path(f"/tmp/startlive-pk-{os.getuid()}/media-v2.sock")


class ObsLocalSocket:
    def __init__(self, *, cancelled):
        self.cancelled = cancelled
        self.path = local_media_path()
        self.socket = None

    def _check_cancelled(self):
        if self.cancelled():
            raise TaskCancelled()

    def connect(self, timeout=10):
        deadline = monotonic() + timeout
        last_error = None
        while monotonic() < deadline:
            self._check_cancelled()
            client = None
            try:
                directory = self.path.parent.lstat()
                endpoint = self.path.lstat()
                if (not stat.S_ISDIR(
                        directory.st_mode) or directory.st_uid != os.getuid()
                        or directory.st_mode & 0o077 or not stat.S_ISSOCK(
                            endpoint.st_mode)
                        or endpoint.st_uid != os.getuid()):
                    raise PkError("OBS 媒体通道不属于当前用户")
                client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                client.settimeout(0.05)
                client.connect(str(self.path))
                self.socket = client
                return
            except OSError as error:
                last_error = error
                if client is not None:
                    client.close()
                if error.errno not in (errno.ENOENT, errno.ECONNREFUSED,
                                       errno.EAGAIN):
                    raise PkError(
                        f"无法连接 OBS 本地媒体通道 {self.path}：{error}") from error
                sleep(0.05)
        detail = f"；最后一次连接失败：{last_error}" if last_error else ""
        raise PkError(
            f"未收到 OBS 媒体连接（{self.path}，等待 {timeout} 秒），"
            f"请在 OBS 工具菜单启动 StartLive PK 采集{detail}") from last_error

    def write_exact(self, data):
        sent = 0
        deadline = monotonic() + 10
        while sent < len(data):
            self._check_cancelled()
            try:
                count = self.socket.send(memoryview(data)[sent:])
            except socket.timeout:
                if monotonic() > deadline:
                    raise PkError(
                        f"发送 OBS 采集选择超时（已发送 {sent}/{len(data)} 字节）") from None
                continue
            except OSError as error:
                raise PkError(
                    f"写入 OBS 媒体通道失败（已发送 {sent}/{len(data)} 字节）：{error}") from error
            if not count:
                raise PkError(
                    f"OBS 媒体通道写入返回 0（已发送 {sent}/{len(data)} 字节）")
            sent += count

    def read_exact(self, size):
        output = bytearray()
        deadline = monotonic() + 10
        while len(output) < size:
            self._check_cancelled()
            try:
                data = self.socket.recv(min(size - len(output), 1024 * 1024))
            except socket.timeout:
                if monotonic() > deadline:
                    raise PkError(
                        f"等待 OBS 媒体帧超时（已接收 {len(output)}/{size} 字节）") from None
                continue
            except OSError as error:
                raise PkError(
                    f"读取 OBS 媒体通道失败（已接收 {len(output)}/{size} 字节）：{error}") from error
            if not data:
                raise PkError(
                    f"OBS 已关闭媒体通道（已接收 {len(output)}/{size} 字节）")
            output.extend(data)
            deadline = monotonic() + 10
        return bytes(output)

    def close(self):
        if self.socket is not None:
            self.socket.close()
            self.socket = None
