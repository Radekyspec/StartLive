# module import

# package import
from PySide6.QtCore import Slot

# local package import
import config
import constant
from models.log import get_logger
from models.workers.base import BaseWorker, run_wrapper


class ConstantUpdateWorker(BaseWorker):
    def __init__(self):
        super().__init__(name="配置更新")
        self.logger = get_logger(self.__class__.__name__)

    @Slot()
    @run_wrapper
    def run(self, /) -> None:
        # url = "https://gcore.jsdelivr.net/gh/Radekyspec/StartLive@master/resources/version.json"
        url = "https://ghfast.top/https://raw.githubusercontent.com/Radekyspec/StartLive/refs/heads/master/resources/version.json"
        self.logger.info(f"version.json Request")
        response = config.session.get(url)
        response.encoding = "utf-8"
        self.logger.info("version.json Response")
        response = response.json()
        self.logger.info(f"version.json Result: {response}")
        constant.APP_KEY = response["ak"]
        constant.APP_SECRET = response["as"]
        constant.LIVEHIME_BUILD = response["b"]
        constant.LIVEHIME_VERSION = response["v"]
        constant.HEADERS_WEB = response["hw"]
        constant.HEADERS_APP = response["ha"]
        constant.START_LIVE_AUTH_CSRF = response["start_ac"]
        constant.STOP_LIVE_AUTH_CSRF = response["stop_ac"]

    @staticmethod
    def on_finished():
        config.scan_status["const_updated"] = True