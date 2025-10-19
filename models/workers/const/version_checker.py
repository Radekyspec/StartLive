# module import

# package import
from PySide6.QtCore import Slot
from semver import compare

# local package import
from constant import VERSION
from models.log import get_logger
from models.states import LoginState
from models.workers.base import BaseWorker, run_wrapper


class VersionCheckerWorker(BaseWorker):
    def __init__(self, state: LoginState):
        super().__init__(name="版本检查")
        self.state = state
        self.logger = get_logger(self.__class__.__name__)
        self._session.cookies.clear()
        self._latest_version = None

    @Slot()
    @run_wrapper
    def run(self, /) -> None:
        # url = "https://gcore.jsdelivr.net/gh/Radekyspec/StartLive@master/resources/version.json"
        url = "https://gh.vtbs.ai/https://api.github.com/repos/Radekyspec/StartLive/releases/latest"
        self.logger.info(f"releases Request")
        response = self._session.get(url)
        response.encoding = "utf-8"
        self.logger.info("releases Response")
        response = response.json()
        latest_tag = response["tag_name"]
        if compare(VERSION, latest_tag) < 0:
            self._latest_version = latest_tag
            self.logger.info(f"New version available: {latest_tag}")

    @Slot()
    def on_finished(self):
        self._session.close()
        if self._latest_version is not None:
            self.state.versionChecked.emit(self._latest_version)
