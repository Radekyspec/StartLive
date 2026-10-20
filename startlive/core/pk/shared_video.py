"""OS-locked latest-frame mailbox and bounded, reference-owned buffer leases."""
import ctypes
import errno
import mmap
import os
import stat
import weakref
from threading import Lock

from startlive.core.constant.pk_media import SHARED_CAPACITY, SHARED_HEADER
from startlive.core.exceptions import PkProtocolError
from startlive.core.pk.states.session import MediaPacket


class FramePool:
    def __init__(self, limit=6):
        self.limit = limit
        self._lock = Lock()
        self._free = []
        self.allocations = self.count = self.misses = 0

    def acquire(self, size):
        with self._lock:
            if self._free:
                storage = self._free.pop()
            elif self.count < self.limit:
                storage = None
                self.count += 1
            else:
                self.misses += 1
                return None
            if storage is None or len(storage) < size:
                storage = bytearray(size)
                self.allocations += 1
        # All derived views retain this ctypes owner. Return storage only after
        # the LAST view disappears, even if the MediaPacket was already dropped.
        owner = (ctypes.c_ubyte * size).from_buffer(storage)
        weakref.finalize(owner, self._release, storage)
        return memoryview(owner).cast("B")

    def _release(self, storage):
        with self._lock:
            self._free.append(storage)


class SharedVideoReader:
    def __init__(self, token, *, pool=None):
        if len(token) != 32 or any(c not in "0123456789abcdef" for c in token):
            raise PkProtocolError("Invalid OBS shared memory identifier")
        self.pool = pool if pool is not None else FramePool()
        self.sequence = 0
        self.fd = self.mapping = self.mutex = self.address = self.view = None
        self.semaphore = None
        self.skipped = self.busy = self.frames = self.bytes_copied = 0
        try:
            if os.name == "nt":
                self._open_windows(token)
            else:
                self._open_posix(token)
        except BaseException:
            self.close()
            raise

    def _open_windows(self, token):
        from ctypes import wintypes as w
        api = self.api = ctypes.WinDLL("kernel32", use_last_error=True)
        api.OpenFileMappingW.argtypes = [w.DWORD, w.BOOL, w.LPCWSTR]
        api.OpenFileMappingW.restype = w.HANDLE
        api.MapViewOfFile.argtypes = [w.HANDLE, w.DWORD, w.DWORD, w.DWORD,
                                      ctypes.c_size_t]
        api.MapViewOfFile.restype = ctypes.c_void_p
        api.OpenMutexW.argtypes = [w.DWORD, w.BOOL, w.LPCWSTR]
        api.OpenMutexW.restype = w.HANDLE
        api.WaitForSingleObject.argtypes = [w.HANDLE, w.DWORD]
        api.WaitForSingleObject.restype = w.DWORD
        api.ReleaseMutex.argtypes = [w.HANDLE]
        api.UnmapViewOfFile.argtypes = [ctypes.c_void_p]
        api.CloseHandle.argtypes = [w.HANDLE]
        name = "Local\\StartLive.PkVideo." + token
        self.mapping = api.OpenFileMappingW(4, False, name)
        self.mutex = api.OpenMutexW(0x100001, False, name + ".lock")
        if not self.mapping or not self.mutex:
            raise PkProtocolError("OBS shared memory session is unavailable")
        self.address = api.MapViewOfFile(self.mapping, 4, 0, 0, SHARED_CAPACITY)
        if not self.address:
            raise PkProtocolError("Cannot map OBS video memory")
        self.view = memoryview(
            (ctypes.c_ubyte * SHARED_CAPACITY).from_address(self.address)).cast(
            "B").toreadonly()

    def _open_posix(self, token):
        from ctypes.util import find_library
        api = ctypes.CDLL(None, use_errno=True)
        if not hasattr(api, "shm_open"):
            api = ctypes.CDLL(find_library("rt"), use_errno=True)
        api.shm_open.argtypes = [ctypes.c_char_p, ctypes.c_int, ctypes.c_uint]
        api.shm_open.restype = ctypes.c_int
        api.shm_unlink.argtypes = [ctypes.c_char_p]
        self.posix_api = api
        api.sem_open.argtypes = [ctypes.c_char_p, ctypes.c_int]
        api.sem_open.restype = ctypes.c_void_p
        for operation in ("sem_trywait", "sem_post", "sem_close"):
            getattr(api, operation).argtypes = [ctypes.c_void_p]
        api.sem_unlink.argtypes = [ctypes.c_char_p]
        name = ("/slpk-m-" + token[:22]).encode("ascii")
        lock_name = ("/slpk-l-" + token[:22]).encode("ascii")
        self.fd = api.shm_open(name, os.O_RDONLY, 0)
        if self.fd < 0:
            self.fd = None
            raise PkProtocolError("OBS shared memory session is unavailable")
        info = os.fstat(self.fd)
        # Darwin shm fstat omits S_IFREG and reports a page-rounded length;
        # Linux reports S_IFREG and the exact ftruncate length.
        rounded_capacity = (
                                   SHARED_CAPACITY + mmap.PAGESIZE - 1) // mmap.PAGESIZE * mmap.PAGESIZE
        if (stat.S_IFMT(info.st_mode) not in (0,
                                              stat.S_IFREG) or info.st_uid != os.getuid()
                or info.st_mode & 0o077 or not SHARED_CAPACITY <= info.st_size <= rounded_capacity):
            raise PkProtocolError("Invalid OBS shared memory file")
        self.mapping = mmap.mmap(self.fd, SHARED_CAPACITY,
                                 access=mmap.ACCESS_READ)
        self.view = memoryview(self.mapping)
        self.semaphore = api.sem_open(lock_name, 0)
        if self.semaphore in (None, ctypes.c_void_p(-1).value):
            self.semaphore = None
            raise PkProtocolError("OBS shared memory lock is unavailable")
        # Every connection has a new token. Handles survive unlink and this
        # session leaves no named file if either process subsequently crashes.
        if api.shm_unlink(name):
            raise PkProtocolError("Cannot retire OBS shared memory name")
        if api.sem_unlink(lock_name):
            raise PkProtocolError("Cannot retire OBS shared lock name")

    def _lock(self):
        if os.name == "nt":
            result = self.api.WaitForSingleObject(self.mutex, 0)
            if result == 0x80:
                self.api.ReleaseMutex(self.mutex)
                raise PkProtocolError(
                    "OBS stopped while writing a shared frame")
            if result == 0x102:
                return False
            if result != 0:
                raise PkProtocolError("OBS video lock failed")
        else:
            if self.posix_api.sem_trywait(self.semaphore):
                if ctypes.get_errno() in (errno.EAGAIN, errno.EINTR):
                    return False
                raise PkProtocolError("OBS video lock failed")
        return True

    def _unlock(self):
        if os.name == "nt":
            self.api.ReleaseMutex(self.mutex)
        else:
            self.posix_api.sem_post(self.semaphore)

    def snapshot(self, notice_sequence):
        if not self._lock():
            self.busy += 1
            return None
        try:
            magic, version, sequence, stamp, width, height, fmt, cs, color_range, size = SHARED_HEADER.unpack_from(
                self.view)
            valid = (
                    magic == b"SLVF" and version == 2 and sequence >= notice_sequence
                    and 0 < width <= 3840 and 0 < height <= 2160
                    and fmt in (1, 2) and cs in (1, 2) and color_range in (
                        1, 2))
            expected = width * height * 4 if fmt == 1 else width * height * 3 // 2
            if not valid or size != expected or (
                    fmt == 2 and (width % 2 or height % 2)):
                raise PkProtocolError("Invalid OBS shared video frame")
            if sequence <= self.sequence:
                return None
            owned = self.pool.acquire(size)
            if owned is None:
                return None
            owned[:] = self.view[SHARED_HEADER.size:SHARED_HEADER.size + size]
            self.skipped += max(0,
                                sequence - self.sequence - 1) if self.sequence else 0
            self.sequence = sequence
            self.frames += 1
            self.bytes_copied += size
            return MediaPacket(1, stamp, width, height,
                               payload=owned.toreadonly(),
                               pixel_format="bgra" if fmt == 1 else "nv12",
                               colorspace="ITU601" if cs == 1 else "ITU709",
                               color_range="MPEG" if color_range == 1 else "JPEG")
        finally:
            self._unlock()

    def close(self):
        if self.view is not None:
            self.view.release()
            self.view = None
        if os.name == "nt":
            if self.address:
                self.api.UnmapViewOfFile(self.address)
            for handle in (self.mapping, self.mutex):
                if handle:
                    self.api.CloseHandle(handle)
        else:
            if self.mapping is not None:
                self.mapping.close()
            if self.fd is not None:
                os.close(self.fd)
            if self.semaphore is not None:
                self.posix_api.sem_close(self.semaphore)
                self.semaphore = None
        self.fd = self.mapping = self.mutex = self.address = None
