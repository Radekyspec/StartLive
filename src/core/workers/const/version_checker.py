# module import
from typing import Callable

# package import
from semver import compare

# local package import
from src.core.constant import VERSION
from src.core.log import get_logger
from src.core.workers.base import BaseWorker


class VersionCheckerWorker(BaseWorker):
    def __init__(self, *args, **kwargs):
        super().__init__(name="版本检查", *args, **kwargs)
        self.logger = get_logger(self.__class__.__name__)
        self._session.cookies.clear()
        self._latest_version = None

    def run(self, report_progress: Callable | None, *args, **kwargs):
        # url = "https://gcore.jsdelivr.net/gh/Radekyspec/StartLive@master/resources/version.json"
        url = "https://gh.bydfk.com/https://api.github.com/repos/Radekyspec/StartLive/releases/latest"
        self.logger.info(f"releases Request")
        response = self._session.get(url)
        response.encoding = "utf-8"
        self.logger.info("releases Response")
        response = response.json()
        latest_tag = response["tag_name"]
        if compare(VERSION, latest_tag) < 0:
            self._latest_version = latest_tag
            self.logger.info(f"New version available: {latest_tag}")
        self._session.close()
        return self._latest_version
