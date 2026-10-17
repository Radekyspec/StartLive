"""Bounded thread-to-asyncio OBS handoff: one video frame, 100 ms of audio."""
from collections import deque
from threading import Lock
from time import monotonic
import asyncio

from startlive.core.pk.states.video_crop import VideoCrop


class MediaBuffer:
    def __init__(self):
        self._lock = Lock()
        self._video_crop = VideoCrop()
        self._video = None
        self._audio = deque()
        self._audio_frames = 0
        self._audio_dropped_frames = 0
        self._arrivals = {}
        # Producer callbacks execute on other threads. Each loop owns its own
        # Future; the producer schedules notifications on that loop.
        self._waiters = {1: [], 2: []}

    @staticmethod
    def _notify(future):
        if not future.done():
            future.set_result(None)

    @staticmethod
    def _wake(waiters):
        for loop, future in waiters:
            try:
                loop.call_soon_threadsafe(MediaBuffer._notify, future)
            except RuntimeError:
                # Shutdown can close a loop after it deregisters its waiter.
                pass

    @property
    def video_crop(self):
        with self._lock:
            return self._video_crop

    @video_crop.setter
    def video_crop(self, crop):
        if not isinstance(crop, VideoCrop):
            raise TypeError("expected VideoCrop")
        with self._lock:
            self._video_crop = crop

    def push(self, packet):
        with self._lock:
            self._arrivals[packet.kind] = monotonic()
            if packet.kind == 1:
                self._video = packet
            else:
                self._audio.append(packet)
                self._audio_frames += packet.frames
                while self._audio and self._audio_frames > 4800:
                    dropped = self._audio.popleft().frames
                    self._audio_frames -= dropped
                    self._audio_dropped_frames += dropped
            waiters = tuple(self._waiters[packet.kind])
        self._wake(waiters)

    def _take_locked(self, kind):
        if kind == 1:
            result, self._video = self._video, None
            return result
        if self._audio:
            result = self._audio.popleft()
            self._audio_frames -= result.frames
            return result
        return None

    def take(self, kind):
        with self._lock:
            return self._take_locked(kind)

    async def wait_for_packet(self, kind, timeout, *, running=lambda: True):
        """Wait without polling; a producer can safely call push from any thread.

        Checking the queue and registering the waiter under one lock avoids the
        lost-notification race between a synchronous take() and awaiting data.
        A track's stop() calls wake(), so shutdown is not delayed by timeout.
        """
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while True:
            with self._lock:
                if not running():
                    return None
                if packet := self._take_locked(kind):
                    return packet
                future = loop.create_future()
                waiter = (loop, future)
                self._waiters[kind].append(waiter)
            try:
                # A Future plus timeout avoids creating an Event.wait task
                # and the extra wait_for callback hops on every audio packet.
                async with asyncio.timeout(max(0, deadline - loop.time())):
                    await future
            finally:
                with self._lock:
                    self._waiters[kind].remove(waiter)

    def wake(self, kind):
        """Wake consumers whose track was stopped without changing the queue."""
        with self._lock:
            waiters = tuple(self._waiters[kind])
        self._wake(waiters)

    def clear(self):
        with self._lock:
            self._arrivals.clear()
            self._video = None
            self._audio.clear()
            self._audio_frames = 0
            self._audio_dropped_frames = 0

    def audio_snapshot(self):
        with self._lock:
            return {"queued_ms": self._audio_frames / 48,
                    "dropped_ms": self._audio_dropped_frames / 48}

    def freshness(self, *, now=None, max_age=2):
        """Track arrivals independently of consumption; packet clocks are remote."""
        now = monotonic() if now is None else now
        with self._lock:
            return tuple(kind in self._arrivals and 0 <= now - self._arrivals[
                kind] <= max_age
                         for kind in (1, 2))
