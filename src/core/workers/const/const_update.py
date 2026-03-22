# module import
from json import loads
from typing import Callable

# local package import
from src.core import app_state, constant
# package import
from src.core.app_state import dumps
from src.core.cache import get_cache_path
from src.core.constant import CacheType
from src.core.log import get_logger
from src.core.workers.base import BaseWorker


class ConstantUpdateWorker(BaseWorker):
    def __init__(self, *args, **kwargs):
        super().__init__(name="配置更新", *args, **kwargs)
        self.logger = get_logger(self.__class__.__name__)
        self._base_dir, self._const_path = get_cache_path(CacheType.CONFIG,
                                                          "version.json")
        self._session.cookies.clear()

    def run(self, report_progress: Callable | None, *args, **kwargs):
        # url = "https://gcore.jsdelivr.net/gh/Radekyspec/StartLive@master/resources/version.json"
        self._load_from_file()
        url = "https://gh.bydfk.com/https://raw.githubusercontent.com/Radekyspec/StartLive/refs/heads/master/resources/version.json"
        self.logger.info(f"version.json Request")
        response = self._session.get(url)
        response.encoding = "utf-8"
        self.logger.info("version.json Response")
        response = response.json()
        self.logger.info(f"version.json Result: {response}")
        self._update_const(response)
        self._save_to_file(response)
        self._session.close()

    def _load_from_file(self):
        if not self._const_path.exists():
            return
        with open(self._const_path, "r", encoding="utf-8") as f:
            self._update_const(loads(f.read()))

    def _save_to_file(self, response):
        with open(self._const_path, "w", encoding="utf-8") as f:
            f.write(dumps(response))

    @staticmethod
    def _update_const(response):
        constant.APP_KEY = response["ak"]
        constant.APP_SECRET = response["as"]
        constant.LIVEHIME_BUILD = response["b"]
        constant.LIVEHIME_VERSION = response["v"]
        constant.HEADERS_WEB = response["hw"]
        constant.HEADERS_APP = response["ha"]
        constant.START_LIVE_AUTH_CSRF = response["start_ac"]
        constant.STOP_LIVE_AUTH_CSRF = response["stop_ac"]

    @Slot()
    def on_finished(self):
        app_state.scan_status["const_updated"] = True
        self._state.constUpdated.emit()
