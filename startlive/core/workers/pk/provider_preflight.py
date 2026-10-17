"""Load native media dependencies in the existing worker pool."""
from startlive.core.workers.base import LongLiveWorker


class PkProviderPreflightWorker(LongLiveWorker):
    def __init__(self, presenter, check=None):
        super().__init__(name="检查视频 PK 组件", presenter=presenter,
                         with_session=False)
        self.check = check

    def run(self, report_progress, *args, **kwargs):
        self.raise_if_cancelled()
        if self.check is None:
            from startlive.core.pk.provider_readiness import \
                ensure_video_provider_ready
            check = ensure_video_provider_ready
        else:
            check = self.check
        check()
        self.raise_if_cancelled()
