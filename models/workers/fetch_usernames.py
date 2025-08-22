# module import
from functools import partial
from json import loads
from time import sleep

from PySide6.QtCore import Slot
from keyring import get_password
from requests import Session

# local package import
import config
import constant
from constant import *
from models.log import get_logger
from models.workers.base import BaseWorker, run_wrapper
from sign import livehime_sign


class FetchUsernamesWorker(BaseWorker):
    def __init__(self, skip_user: str):
        super().__init__(name="用户名更新")
        self._current_user = skip_user
        self.logger = get_logger(self.__class__.__name__)

    @Slot()
    @run_wrapper
    def run(self, /) -> None:
        if not config.scan_status["scanned"]:
            return
        url = "https://api.bilibili.com/x/web-interface/nav"
        session = Session()
        session.headers.update(constant.HEADERS_APP)
        if config.app_settings["use_proxy"]:
            session.get = partial(session.get, verify=False, timeout=5)
            session.post = partial(session.post, verify=False, timeout=5)
            session.trust_env = True
        else:
            session.get = partial(session.get, verify=True, timeout=5)
            session.post = partial(session.post, verify=True, timeout=5)
            session.trust_env = False
        for idx, key in enumerate(config.usernames):
            if key == self._current_user or (
            cookies := get_password(KEYRING_SERVICE_NAME,
                                    key)) is None:
                continue
            sleep(1)
            cookies = loads(cookies)
            self.logger.info(f"fetch username of {key} Request")
            session.cookies.clear()
            session.cookies.update(cookies)
            session.cookies.set("appkey", constant.APP_KEY,
                                domain="bilibili.com",
                                path="/")
            response = session.get(
                url,
                params=livehime_sign({},
                                     access_key=False,
                                     build=False,
                                     version=False))
            response.encoding = "utf-8"
            self.logger.info(f"fetch username of {key} Response")
            response = response.json()
            if response["code"] != 0:
                continue
            config.usernames[key] = USERNAME_DISPLAY_TEMPLATE.format(
                response["data"]["uname"],
                response["data"]["mid"]
            )
            self.logger.info(f"fetch username of {key} Completed")
