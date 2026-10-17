from time import time
from typing import Callable
from urllib.parse import quote

# local package import
from startlive.core import app_state
from startlive.core.constant import *
from startlive.core.log import get_logger
from startlive.core.sign import ticket_hmac_sha256
from startlive.core.workers.base import BaseWorker, Presenter


class TicketFetchWorker(BaseWorker):
    def __init__(self, presenter: Presenter):
        self._account_generation, self._account_cookies = app_state.capture_account_context()
        super().__init__(name="ticket获取", headers_type=HeadersType.WEB,
                         presenter=presenter,
                         account_cookies=self._account_cookies)
        self.logger = get_logger(self.__class__.__name__)

    def run(self, report_progress: Callable | None, *args, **kwargs):

        with app_state.account_guard(self._account_generation):
            cookies = dict(self._account_cookies)
        if int(cookies.get("bili_ticket_expires", 0)) < int(
                time()):
            self.logger.info("buvid_ticket Request")
            ticket_param = {
                "key_id": "ec02",
                "hexsign": ticket_hmac_sha256(int(time())),
                "context[ts]": int(time()),
                "csrf": cookies.get("bili_jct", "")
            }
            response = self._session.post(
                "https://api.bilibili.com/bapis/bilibili.api.ticket.v1.Ticket/GenWebTicket",
                params=ticket_param)
            self.logger.info("buvid_ticket Response")
            response.encoding = "utf-8"
            response = response.json()
            cookies.update({
                "bili_ticket": response["data"]["ticket"],
                "bili_ticket_expires": str(response["data"]["created_at"] +
                                           response["data"]["ttl"]),
            })
            with app_state.account_guard(self._account_generation):
                app_state.cookies_dict.update({
                    "bili_ticket": cookies["bili_ticket"],
                    "bili_ticket_expires": cookies["bili_ticket_expires"],
                })

        if not cookies.get(
                "buvid3") or not cookies.get("buvid4"):
            self.logger.info("buvid3 Request")
            response = self._session.get(
                "https://api.bilibili.com/x/frontend/finger/spi")
            self.logger.info("buvid3 Response")
            response.encoding = "utf-8"
            response = response.json()
            with app_state.account_guard(self._account_generation):
                app_state.cookies_dict.update({
                    "buvid3": response["data"]["b_3"],
                    "buvid4": quote(response["data"]["b_4"]),
                })
        return self._account_generation
