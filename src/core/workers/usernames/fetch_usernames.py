from time import sleep
from typing import Callable

from requests.cookies import cookiejar_from_dict

# local package import
from src.core import app_state
from src.core.constant import *
from src.core.credentials import CredentialStore
from src.core.log import get_logger
from src.core.sign import livehime_sign
from src.core.workers.base import BaseWorker


class FetchUsernamesWorker(BaseWorker):
    def __init__(self, skip_user: str):
        super().__init__(name="用户名更新", headers_type=HeadersType.WEB,
                         inherit_account_cookies=False)
        self._current_user = skip_user
        self._store = CredentialStore()
        self.logger = get_logger(self.__class__.__name__)

    def run(self, report_progress: Callable | None, *args, **kwargs):
        if not app_state.scan_status["scanned"]:
            return
        url = "https://api.bilibili.com/x/web-interface/nav"
        keys = tuple(app_state.usernames)
        baseline = self._session.cookies.copy()
        refreshed_usernames = {}
        for key in keys:
            if key == self._current_user:
                continue
            sleep(1)
            cookies = self._store.read(key)
            self.logger.info(f"fetch username of {key} Request")
            self._session.cookies.clear()
            self._session.cookies.update(baseline)
            cookiejar_from_dict(
                cookies, cookiejar=self._session.cookies, overwrite=True
            )
            response = self._session.get(
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
            refreshed_usernames[key] = USERNAME_DISPLAY_TEMPLATE.format(
                response["data"]["uname"],
                response["data"]["mid"]
            )
            self.logger.info(f"fetch username of {key} Completed")
        app_state.usernames.update(refreshed_usernames)
