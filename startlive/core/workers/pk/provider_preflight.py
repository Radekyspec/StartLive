"""Load the fixed RTC provider stack in the existing worker pool."""
from importlib import import_module

from startlive.core.exceptions import PkError
from startlive.core.workers.base import LongLiveWorker


class PkProviderPreflightWorker(LongLiveWorker):
    def __init__(self, presenter):
        super().__init__(name="检查视频 PK 组件", presenter=presenter,
                         with_session=False)

    def run(self, report_progress, *args, **kwargs):
        for name in ("aiortc", "av", "startlive.core.pk.rtc_connection",
                     "startlive.core.pk.rtc_media"):
            self.raise_if_cancelled()
            try:
                import_module(name)
            except (ImportError, OSError) as error:
                raise PkError(
                    f"加载 PK 组件 {name} 失败：{type(error).__name__}: {error}。"
                    "请安装或修复 StartLive 的 PK 组件") from error
        self.raise_if_cancelled()
