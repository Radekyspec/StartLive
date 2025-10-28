# module import
from json import loads
from os import makedirs
from os.path import join, isdir, expanduser, abspath
from platform import system

# package import
from PySide6.QtCore import Slot

# local package import
import app_state
import constant
from app_state import dumps
from models.log import get_logger
from models.states import LoginState
from models.workers.base import BaseWorker, run_wrapper


class ConstantUpdateWorker(BaseWorker):
    def __init__(self, state: LoginState):
        super().__init__(name="配置更新")
        self._state = state
        self.logger = get_logger(self.__class__.__name__)
        self._get_const_path()
        self._session.cookies.clear()

    def _get_const_path(self, *, is_makedir: bool = True) -> None:
        if (_arch := system()) == "Windows":
            try:
                self._base_dir = abspath(__compiled__.containing_dir)
            except NameError:
                self._base_dir = abspath(".")
            self._base_dir = join(self._base_dir, "config")
            self._const_path = join(self._base_dir, "version.json")
        elif _arch == "Linux":
            self._base_dir = join(expanduser("~"), ".cache", "StartLive",
                                  "config")
            self._const_path = join(self._base_dir, "version.json")
        elif _arch == "Darwin":
            self._base_dir = join(expanduser("~"), "Library",
                                  "Application Support", "StartLive")
            self._const_path = join(self._base_dir, "version.json")
        else:
            raise ValueError("Unsupported system")
        if is_makedir:
            makedirs(self._base_dir, exist_ok=True)

    @Slot()
    @run_wrapper
    def run(self, /) -> None:
        # url = "https://gcore.jsdelivr.net/gh/Radekyspec/StartLive@master/resources/version.json"
        self._load_from_file()
        url = "https://gh.vtbs.ai/https://raw.githubusercontent.com/Radekyspec/StartLive/refs/heads/master/resources/version.json"
        self.logger.info(f"version.json Request")
        response = self._session.get(url)
        response.encoding = "utf-8"
        self.logger.info("version.json Response")
        response = response.json()
        self.logger.info(f"version.json Result: {response}")
        self._update_const(response)
        self._save_to_file(response)
        app_state.scan_status["const_updated"] = True

    def _load_from_file(self):
        if not isdir(self._base_dir):
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
        self._state.constUpdated.emit()
        self._session.close()
