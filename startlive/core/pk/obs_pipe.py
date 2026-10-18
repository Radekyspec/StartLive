"""Cancellable Windows named-pipe reader; imports Windows APIs only on use."""
from ctypes import wintypes
from time import monotonic, sleep
import ctypes
import os

from startlive.core.constant.pk_media import PIPE_NAME
from startlive.core.exceptions import TaskCancelled
from startlive.core.exceptions import PkError


class ObsPipe:
    def __init__(self, cancelled=lambda: False):
        if os.name != "nt":
            raise PkError("OBS 原始媒体插件目前支持 Windows")
        self.cancelled = cancelled
        self.handle = None
        self.api = ctypes.WinDLL("kernel32", use_last_error=True)

        class Overlapped(ctypes.Structure):
            _fields_ = [("Internal", ctypes.c_size_t),
                        ("InternalHigh", ctypes.c_size_t),
                        ("Offset", wintypes.DWORD),
                        ("OffsetHigh", wintypes.DWORD),
                        ("hEvent", wintypes.HANDLE)]

        self.Overlapped = Overlapped
        self.api.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD,
                                         wintypes.DWORD,
                                         ctypes.c_void_p, wintypes.DWORD,
                                         wintypes.DWORD, wintypes.HANDLE]
        self.api.CreateFileW.restype = wintypes.HANDLE
        self.api.CreateEventW.argtypes = [ctypes.c_void_p, wintypes.BOOL,
                                          wintypes.BOOL, wintypes.LPCWSTR]
        self.api.CreateEventW.restype = wintypes.HANDLE
        self.api.CloseHandle.argtypes = [wintypes.HANDLE]
        self.api.ReadFile.argtypes = [wintypes.HANDLE, ctypes.c_void_p,
                                      wintypes.DWORD,
                                      ctypes.POINTER(wintypes.DWORD),
                                      ctypes.POINTER(Overlapped)]
        self.api.WaitForSingleObject.argtypes = [wintypes.HANDLE,
                                                 wintypes.DWORD]
        self.api.WaitForSingleObject.restype = wintypes.DWORD
        self.api.GetOverlappedResult.argtypes = [wintypes.HANDLE,
                                                 ctypes.POINTER(Overlapped),
                                                 ctypes.POINTER(wintypes.DWORD),
                                                 wintypes.BOOL]
        self.api.CancelIoEx.argtypes = [wintypes.HANDLE,
                                        ctypes.POINTER(Overlapped)]

    def connect(self, timeout=10):
        deadline = monotonic() + timeout
        while monotonic() < deadline:
            self._check_cancelled()
            # Identification-only prevents a spoofed pipe server impersonating this client.
            handle = self.api.CreateFileW(PIPE_NAME, 0x80000000, 0, None, 3,
                                          0x40000000 | 0x100000 | 0x10000, None)
            if handle != wintypes.HANDLE(-1).value:
                self.handle = handle
                return
            if ctypes.get_last_error() not in (2, 231):
                raise PkError(
                    "无法打开 OBS 媒体管道，请检查插件和当前 Windows 用户")
            sleep(0.05)
        raise PkError(
            "未收到 OBS 媒体连接，请在 OBS 工具菜单启动 StartLive PK 采集")

    def _check_cancelled(self):
        if self.cancelled():
            raise TaskCancelled()

    def read_exact(self, size):
        # One owned allocation avoids repeated megabyte copies while holding
        # Python's GIL, which otherwise starves audio when capturing 1080p.
        output = ctypes.create_string_buffer(size)
        received = 0
        while received < size:
            self._check_cancelled()
            overlap = self.Overlapped()
            overlap.hEvent = self.api.CreateEventW(None, True, False, None)
            if not overlap.hEvent:
                raise PkError("无法创建 OBS 媒体读取事件")
            count = wintypes.DWORD()
            pending = False
            try:
                ok = self.api.ReadFile(self.handle,
                                       ctypes.byref(output, received),
                                       size - received,
                                       ctypes.byref(count),
                                       ctypes.byref(overlap))
                if not ok:
                    if ctypes.get_last_error() != 997:
                        raise PkError("OBS 媒体连接已断开")
                    pending = True
                    deadline = monotonic() + 10
                    while True:
                        self._check_cancelled()
                        wait = self.api.WaitForSingleObject(overlap.hEvent, 50)
                        if wait == 0:
                            break
                        if wait != 258 or monotonic() > deadline:
                            raise PkError("等待 OBS 媒体帧超时")
                    if not self.api.GetOverlappedResult(self.handle,
                                                        ctypes.byref(overlap),
                                                        ctypes.byref(count),
                                                        False):
                        raise PkError("OBS 媒体连接已断开")
                    pending = False
                if not count.value:
                    raise PkError("OBS 媒体连接已断开")
                received += count.value
            finally:
                if pending:
                    self.api.CancelIoEx(self.handle, ctypes.byref(overlap))
                    self.api.WaitForSingleObject(overlap.hEvent, 0xFFFFFFFF)
                self.api.CloseHandle(overlap.hEvent)
        return output.raw

    def close(self):
        if self.handle is not None:
            self.api.CloseHandle(self.handle)
            self.handle = None
