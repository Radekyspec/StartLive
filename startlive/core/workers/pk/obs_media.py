from time import perf_counter

from startlive.core.exceptions import PkProtocolError
from startlive.core.pk.media_wire import read_packet, SharedVideoSetup, \
    VideoNotice
from startlive.core.pk.obs_transport import create_media_connection
from startlive.core.pk.shared_video import SharedVideoReader
from startlive.core.pk.trace import pk_trace
from startlive.core.workers.base import LongLiveWorker


class ObsMediaWorker(LongLiveWorker):
    def __init__(self, presenter, buffers, /, *,
                 connection_factory=create_media_connection, video=True):
        super().__init__(name="OBS 原始媒体采集", presenter=presenter,
                         with_session=False)
        self.buffers = tuple(buffers)
        self.connection_factory = connection_factory
        self.video = video

    def run(self, report_progress, *args, **kwargs):
        pipe = self.connection_factory(cancelled=lambda: not self.is_running)
        shared = None
        stats_at = perf_counter()
        try:
            pipe.connect()
            if report_progress:
                report_progress("connected")
            while self.is_running:
                packet = read_packet(pipe.read_exact)
                if isinstance(packet, SharedVideoSetup):
                    if not self.video:
                        continue
                    if shared is not None:
                        raise PkProtocolError(
                            "Duplicate OBS shared memory setup")
                    shared = SharedVideoReader(packet.token)
                    continue
                if isinstance(packet, VideoNotice):
                    if not self.video:
                        continue
                    if shared is None:
                        raise PkProtocolError(
                            "OBS video arrived before shared memory setup")
                    packet = shared.snapshot(packet.sequence)
                    if packet is None:
                        continue
                if not self.video and packet.kind == 1:
                    continue
                for buffer in self.buffers:
                    buffer.push(packet)
                if shared is not None and perf_counter() - stats_at >= 5:
                    stats_at = perf_counter()
                    pk_trace("obs.shared_video.stats", frames=shared.frames,
                             skipped=shared.skipped, busy=shared.busy,
                             bytes_copied=shared.bytes_copied,
                             pool_allocations=shared.pool.allocations,
                             pool_misses=shared.pool.misses)
        finally:
            if shared is not None:
                shared.close()
            pipe.close()
            for buffer in self.buffers:
                buffer.clear()
