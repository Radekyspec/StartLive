# module import

# package import
from PySide6.QtCore import Slot

# local package import
import config
import constant
from .base import BaseWorker


class ConstantUpdateWorker(BaseWorker):
    def __init__(self):
        super().__init__(name="配置更新")

    @Slot()
    def run(self, /) -> None:
        try:
            # url = "https://gcore.jsdelivr.net/gh/Radekyspec/StartLive@master/resources/version.json"
            url = "https://ghfast.top/https://raw.githubusercontent.com/Radekyspec/StartLive/refs/heads/master/resources/version.json"
            response = config.session.get(url).json()
            constant.APP_KEY = response["ak"]
            constant.APP_SECRET = response["as"]
            constant.LIVEHIME_BUILD = response["b"]
            constant.LIVEHIME_VERSION = response["v"]
            constant.HEADERS_WEB = response["hw"]
            constant.HEADERS_APP = response["ha"]
            constant.START_LIVE_AUTH_CSRF = response["start_ac"]
            constant.STOP_LIVE_AUTH_CSRF = response["stop_ac"]
        except Exception:
            pass
        finally:
            self.finished = True