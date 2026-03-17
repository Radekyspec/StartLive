# module import
from typing import Callable

from ..base import BaseWorker
from ... import app_state
from ...exceptions import AnnounceUpdateError
from ...log import get_logger
from ...sign import livehime_sign, order_payload


class AnnounceUpdateWorker(BaseWorker):
    def __init__(self, content: str, *args, **kwargs):
        super().__init__(name="主播公告更新", *args, **kwargs)
        self.content = content
        self.logger = get_logger(self.__class__.__name__)

    def run(self, report_progress: Callable | None, *args, **kwargs):
        url = "https://api.live.bilibili.com/xlive/app-blink/v1/room/AnnounceCommit"
        announce_data = livehime_sign({})
        announce_data.update(
            {
                "content": self.content,
                "csrf_token": app_state.cookies_dict["bili_jct"],
                "csrf": app_state.cookies_dict["bili_jct"],
                "type": "1",
            }
        )
        announce_data = order_payload(announce_data)
        self.logger.info(f"AnnounceCommit Request")
        response = self._session.post(url, data=announce_data)
        response.encoding = "utf-8"
        self.logger.info("AnnounceCommit Response")
        # print(response.text)
        response.raise_for_status()
        response = response.json()
        self.logger.info(f"AnnounceCommit Result: {response}")
        if response["code"] != 0:
            raise AnnounceUpdateError(response["message"])
        app_state.room_info["announcement"] = self.content
        self._session.close()
