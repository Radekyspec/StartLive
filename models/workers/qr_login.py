# module import
from time import time_ns

# package import
from PySide6.QtCore import Slot

# local package import
import config
from .base import BaseWorker


class QRLoginWorker(BaseWorker):
    def __init__(self, parent_window: "MainWindow"):
        super().__init__(name="登录二维码")
        self.parent_window = parent_window

    @Slot()
    def run(self):
        # logic from run_qr_login()
        generate_url = "https://passport.bilibili.com/x/passport-login/web/qrcode/generate"
        ts = str(time_ns())
        gen_data = {
            "source": "live_pc",
            "go_url": "https://live.bilibili.com/"
                      "p/html/live-pc-blink/mini-login-v2/?"
                      f"livehime_create_ts={ts[:13]}&livehime_ts={ts[:10]}",
            "web_location": "0.0"
        }
        try:
            response = config.session.get(generate_url, params=gen_data).json()
            config.scan_status["qr_key"] = response["data"]["qrcode_key"]
            config.scan_status["qr_url"] = response["data"]["url"]
            self.parent_window.update_qr_image(response["data"]["url"])
        except Exception as e:
            self.exception = e
        finally:
            self.finished = True
