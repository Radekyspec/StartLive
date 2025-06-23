# module import

# package import
from PySide6.QtCore import Slot

# local package import
import config
from sign import livehime_sign, order_payload
from .base import BaseWorker


class StartLiveWorker(BaseWorker):
    def __init__(self, parent_window: "StreamConfigPanel", area):
        super().__init__(name="开播任务")
        self.area = area
        self.parent_window = parent_window

    @Slot()
    def run(self, /) -> None:
        live_url = "https://api.live.bilibili.com/room/v1/Room/startLive"
        try:
            # self.fetch_upstream()
            live_data = livehime_sign({
                "room_id": config.room_info["room_id"],
                "area_v2": self.area,
                "type": 2,
            })
            live_data.update({
                "csrf_token": config.cookies_dict["bili_jct"],
                "csrf": config.cookies_dict["bili_jct"]
            })
            live_data = order_payload(live_data)
            response = config.session.post(live_url, data=live_data)
            response.encoding = "utf-8"
            response = response.json()
            match response["code"]:
                case 0:
                    config.stream_status["stream_addr"] = \
                        response["data"]["rtmp"][
                            "addr"]
                    config.stream_status["stream_key"] = \
                        response["data"]["rtmp"][
                            "code"]
                case 60024:
                    config.stream_status.update({
                        "required_face": True,
                        "face_url": response["data"]["qr"]
                    })
                case _:
                    raise RuntimeError(response["message"])
        except Exception as e:
            self.parent_window.start_btn.setEnabled(True)
            self.parent_window.stop_btn.setEnabled(False)
            # self.parent_window.parent_combo.setEnabled(True)
            # self.parent_window.child_combo.setEnabled(True)
            self.parent_window.save_area_btn.setEnabled(True)
            self.exception = e
        finally:
            self.finished = True

    @staticmethod
    def fetch_upstream():
        stream_url = "https://api.live.bilibili.com/xlive/app-blink/v1/live/FetchWebUpStreamAddr"
        stream_data = livehime_sign({
            "backup_stream": 0,
        })
        stream_data.update({
            "csrf_token": config.cookies_dict["bili_jct"],
            "csrf": config.cookies_dict["bili_jct"]
        })
        stream_data = order_payload(stream_data)
        response = config.session.post(stream_url, data=stream_data)
        response.encoding = "utf-8"
        response = response.json()
        return response["data"]["addr"]["addr"], response["data"]["addr"][
            "code"]
