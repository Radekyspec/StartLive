"""Short media deadlines without blocking the RTC event loop.

Deadlines use perf_counter throughout: Python 3.11's Windows monotonic clock
uses GetTickCount64 (15.6 ms), unlike QueryPerformanceCounter.
"""
import asyncio
from sys import platform
from time import perf_counter, sleep


def _sleep_until(deadline):
    # Compute remaining time in the worker, excluding executor queue latency.
    remaining = deadline - perf_counter()
    if remaining > 0:
        sleep(remaining)


async def wait_until(deadline):
    if deadline <= perf_counter():
        return
    if platform == "win32":
        # Python 3.11 uses a high-resolution waitable timer for time.sleep.
        # asyncio's Windows timeout can round a sub-ms wait to a ~16 ms tick.
        # No busy loop or process-wide timer-resolution changes are needed.
        await asyncio.to_thread(_sleep_until, deadline)
    else:
        while (remaining := deadline - perf_counter()) > 0:
            await asyncio.sleep(remaining)
