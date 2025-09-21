from functools import partial

# package import
from PySide6.QtCore import Slot

# local package import
import config
from constant import CoverStatus
from models.log import get_logger
from models.workers.base import BaseWorker, run_wrapper
from sign import livehime_sign, order_payload
from .cover_state_update import CoverStateUpdateWorker
from .start_live import StartLiveWorker
from ..states import LoginState


class FetchPreLiveWorker(BaseWorker):
    def __init__(self):
        super().__init__(name="房间信息")
        self.logger = get_logger(self.__class__.__name__)

    def _fetch_room_info(self):
        live_info_url = "https://api.live.bilibili.com/xlive/app-blink/v1/room/GetInfo"
        info_data = livehime_sign({"uId": config.cookies_dict["DedeUserID"]})
        info_data = order_payload(info_data)
        self.logger.info("live_info Request")
        response = self._session.get(live_info_url, params=info_data)
        response.encoding = "utf-8"
        self.logger.info("live_info Response")
        response = response.json()
        self.logger.info(f"live_info Result: {response}")
        config.room_info.update(
            {
                "room_id": response["data"]["room_id"],
                "parent_area": response["data"]["parent_name"],
                "area": response["data"]["area_v2_name"],
            }
        )
        if response["data"]["live_status"] == 1:
            config.stream_status["live_status"] = True
            # [0.3.4] fix fetch upstream
            # Here we choose to start live again because as observation of duplicate live
            # The API only returns a message="重复开播" with streaming address
            # Which seems like have no other side effect
            # Subject to change if there is an unknown side effect
            StartLiveWorker.start_live(self._session,
                                       response["data"]["area_v2_id"])
        config.scan_status["room_updated"] = True

    @Slot()
    @run_wrapper
    def run(self, /) -> None:
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
        config.room_info.update({
            "cover_audit_reason": response["data"]["cover"]["auditReason"],
            "cover_url": response["data"]["cover"]["url"],
            "cover_status": response["data"]["cover"]["auditStatus"],
            "title": response["data"]["title"],
        })
        self._fetch_room_info()

    @Slot()
    def on_finished(self, parent_window: "StreamConfigPanel",
                    state: LoginState):
        parent_window.title_input.setText(config.room_info["title"])
        parent_window.title_input.textEdited.connect(
            lambda: parent_window.save_title_btn.setEnabled(True))
        if config.stream_status["live_status"]:
            parent_window.addr_input.setText(
                config.stream_status["stream_addr"])
            parent_window.key_input.setText(
                config.stream_status["stream_key"])
            parent_window.start_btn.setEnabled(False)
            parent_window.parent_window.tray_start_live_action.setEnabled(False)
            parent_window.stop_btn.setEnabled(True)
            parent_window.parent_window.tray_stop_live_action.setEnabled(True)
        parent_window.cover_audit_state()
        if config.room_info["cover_status"] == CoverStatus.AUDIT_IN_PROGRESS:
            # add updating logic
            cover_state_updater = CoverStateUpdateWorker()
            parent_window.parent_window.add_thread(
                cover_state_updater,
                on_finished=partial(
                    cover_state_updater.on_finished, parent_window),
            )
        state.roomUpdated.emit()
        self._session.close()
