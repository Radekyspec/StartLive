from typing import Callable

# local package import
from src.core import app_state
# package import
from src.core.log import get_logger
from src.core.sign import livehime_sign, order_payload
from src.core.workers.base import BaseWorker, Presenter
from src.core.workers.live import StartLiveWorker


class FetchPreLiveWorker(BaseWorker):
    def __init__(self, presenter: Presenter, /):
        super().__init__(name="PreLive信息", presenter=presenter)
        self.logger = get_logger(self.__class__.__name__)

    def _fetch_room_info(self):
        live_info_url = "https://api.live.bilibili.com/xlive/app-blink/v1/room/GetInfo"
        info_data = livehime_sign({"uId": app_state.cookies_dict["DedeUserID"]})
        info_data = order_payload(info_data)
        self.logger.info("live_info Request")
        response = self._session.get(live_info_url, params=info_data)
        response.encoding = "utf-8"
        self.logger.info("live_info Response")
        response = response.json()
        app_state.room_info.update(
            {
                "room_id": response["data"]["room_id"],
                "parent_area": response["data"]["parent_name"],
                "area": response["data"]["area_v2_name"],
                "area_code": response["data"]["area_v2_id"]
            }
        )
        if response["data"]["live_status"] == 1:
            app_state.stream_status["live_status"] = True
            # [0.3.4] fix fetch upstream
            # Here we choose to start live again because as observation of duplicate live
            # The API only returns a message="重复开播" with streaming address
            # Which seems like have no other side effect
            # Subject to change if there is an unknown side effect
            StartLiveWorker.start_live(self._session,
                                       response["data"]["area_v2_id"])
        app_state.scan_status["room_updated"] = True

    def run(self, report_progress: Callable | None, *args, **kwargs):
        url = "https://api.live.bilibili.com/xlive/app-blink/v1/preLive/PreLive"
        params = livehime_sign({
            "area": "true",
            "cover": "true",
            "coverVertical": "true",
            "liveDirectionType": 0,
            "mobi_app": "pc_link",
            "schedule": "true",
            "title": "true",
        })
        self.logger.info("PreLive Request")
        response = self._session.get(url, params=params)
        response.encoding = "utf-8"
        self.logger.info("PreLive Response")
        response = response.json()
        self.logger.info(f"PreLive Result: {response}")
        app_state.room_info.update({
            "cover_audit_reason": response["data"]["cover"]["auditReason"],
            "cover_url": response["data"]["cover"]["url"],
            "cover_status": response["data"]["cover"]["auditStatus"],
            "title": response["data"]["title"],
        })
        self._fetch_room_info()
