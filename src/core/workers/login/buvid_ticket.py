from collections.abc import Callable
from time import time
from urllib.parse import quote

# local package import
from src.core import app_state
from src.core.constant import HeadersType
from src.core.log import get_logger
from src.core.sign import ticket_hmac_sha256
from src.core.workers.base import BaseWorker, Presenter


def _current_timestamp() -> int:
    try:
        return int(time())
    except (OverflowError, ValueError) as exc:
        raise RuntimeError("System clock returned an invalid timestamp") from exc


class TicketFetchWorker(BaseWorker):
    def __init__(self, presenter: Presenter):
        super().__init__(name="ticket获取", headers_type=HeadersType.WEB,
                         presenter=presenter)
        self.logger = get_logger(self.__class__.__name__)

    def run(self, report_progress: Callable | None, *args, **kwargs):
        session = self.require_session()
        try:
            ticket_expires = int(
                app_state.cookies_dict.get("bili_ticket_expires", 0)
            )
        except (TypeError, ValueError, OverflowError):
            ticket_expires = 0
        timestamp = _current_timestamp()
        if ticket_expires < timestamp:
            self.logger.info("buvid_ticket Request")
            ticket_param = {
                "key_id": "ec02",
                "hexsign": ticket_hmac_sha256(timestamp),
                "context[ts]": timestamp,
                "csrf": app_state.cookies_dict.get("bili_jct", "")
            }
            response = session.post(
                "https://api.bilibili.com/bapis/bilibili.api.ticket.v1.Ticket/GenWebTicket",
                params=ticket_param)
            self.logger.info("buvid_ticket Response")
            response.encoding = "utf-8"
            response = response.json()
            app_state.cookies_dict["bili_ticket"] = response["data"][
                "ticket"]
            app_state.cookies_dict["bili_ticket_expires"] = str(
                response["data"][
                    "created_at"] + \
                response["data"][
                    "ttl"])

        if not app_state.cookies_dict.get(
                "buvid3") or not app_state.cookies_dict.get("buvid4"):
            self.logger.info("buvid3 Request")
            response = session.get(
                "https://api.bilibili.com/x/frontend/finger/spi")
            self.logger.info("buvid3 Response")
            response.encoding = "utf-8"
            response = response.json()
            app_state.cookies_dict["buvid3"] = response["data"]["b_3"]
            app_state.cookies_dict["buvid4"] = quote(
                response["data"]["b_4"])
