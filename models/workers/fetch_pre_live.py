# module import

# package import
from PySide6.QtCore import Slot

# local package import
import config
from .start_live import StartLiveWorker
from .base import BaseWorker
from sign import livehime_sign, order_payload


class FetchPreLiveWorker(BaseWorker):
    def __init__(self, parent_window: "StreamConfigPanel"):
        super().__init__(name="房间信息")
        self.parent_window = parent_window

    def _fetch_pre_live(self):
        room_info_url = "https://api.live.bilibili.com/xlive/web-ucenter/user/live_info"
        live_info_url = "https://api.live.bilibili.com/xlive/app-blink/v1/room/GetInfo"
        response = config.session.get(room_info_url)
        response.encoding = "utf-8"
        response = response.json()
        config.room_info["room_id"] = response["data"]["room_id"]
        info_data = livehime_sign({"uId": config.cookies_dict["DedeUserID"]})
        info_data = order_payload(info_data)
        response = config.session.get(live_info_url, params=info_data)
        response.encoding = "utf-8"
        response = response.json()
        if response["data"]["live_status"] == 1:
            config.stream_status["live_status"] = True
            addr, code = StartLiveWorker.fetch_upstream()
            self.parent_window.addr_input.setText(addr)
            self.parent_window.key_input.setText(code)
            # Not work?
            # self.parent_window.parent_combo.setCurrentText(
            #     response["data"]["parent_name"]
            # )
            # self.parent_window.child_combo.setCurrentText(
            #     response["data"]["area_v2_name"]
            # )
            self.parent_window.start_btn.setEnabled(False)
            self.parent_window.stop_btn.setEnabled(True)
        config.room_info["parent_area"] = response["data"]["parent_name"]
        config.room_info["area"] = response["data"]["area_v2_name"]
        config.scan_status["room_updated"] = True

    @Slot()
    def run(self, /) -> None:
        url = "https://api.live.bilibili.com/xlive/app-blink/v1/preLive/PreLive"
        params = livehime_sign({
            "area": True,
            "cover": True,
            "coverVertical": True,
            "liveDirectionType": 0,
            "mobi_app": "pc_link",
            "schedule": True,
            "title": True,
        })
        try:
            response = config.session.get(url, params=params)
            response.encoding = "utf-8"
            response = response.json()
            config.room_info["title"] = response["data"]["title"]
            self.parent_window.title_input.setText(
                response["data"]["title"])
            self.parent_window.title_input.textEdited.connect(
                lambda: self.parent_window.save_title_btn.setEnabled(True))
            self._fetch_pre_live()
        except Exception as e:
            self.exception = e
        finally:
            self.finished = True
