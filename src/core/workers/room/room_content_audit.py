from typing import Callable

from src.PySide.log import get_logger
from src.core import app_state
from src.core.constant import TitleStatus
from src.core.exceptions.TitleStatusError import TitleStatusError
from src.core.sign import livehime_sign, order_payload
from src.core.workers.base import BaseWorker


class GetRoomContentAuditWorker(BaseWorker):
    def __init__(self):
        super().__init__(name="GetRoomContentAuditInfo")
        self.logger = get_logger(self.__class__.__name__)

    def run(self, report_progress: Callable | None, *args, **kwargs):
        url = "https://api.live.bilibili.com/xlive/app-blink/v1/room/GetRoomContentAuditInfo"
        params = livehime_sign({
            "csrf": app_state.cookies_dict["bili_jct"],
            "csrf_token": app_state.cookies_dict["bili_jct"],
        })
        params.update({
            "content_type": "1",
            "room_id": app_state.room_info["room_id"],
        })
        params = order_payload(params)
        self.logger.info("GetRoomContentAuditInfo Request")
        response = self._session.get(url, params=params)
        self.logger.info("GetRoomContentAuditInfo Response")
        response.encoding = "utf-8"
        response = response.json()
        self.logger.info(f"GetRoomContentAuditInfo Result: {response}")
        if response["data"] and response["data"]["title_audit_info"] and \
                response["data"]["title_audit_info"][
                    "audit_status"] != TitleStatus.AUDIT_PASSED:
            app_state.room_info["title"] = response["data"]["title"]
            raise TitleStatusError(
                response["data"]["title_audit_info"]["audit_reason"])
