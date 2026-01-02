# module import
from time import time_ns

# package import
from PySide6.QtCore import Slot

# local package import
import app_state
from constant import HeadersType
from models.log import get_logger
from models.workers.base import BaseWorker, run_wrapper


class FetchQRWorker(BaseWorker):
    def __init__(self):
        super().__init__(name="登录二维码", headers_type=HeadersType.WEB)
        self.logger = get_logger(self.__class__.__name__)

    @Slot()
    @run_wrapper
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
        self.logger.info(f"QRGenerate Request")
        response = self._session.get(generate_url, params=gen_data)
        response.encoding = "utf-8"
        self.logger.info("QRGenerate Response")
        response = response.json()
        self.logger.info(f"QRGenerate Result: {response}")
        app_state.scan_status["qr_key"] = response["data"]["qrcode_key"]
        app_state.scan_status["qr_url"] = response["data"]["url"]

    @Slot()
    def on_finished(self, parent_window: "MainWindow"):
        parent_window.update_qr_image(app_state.scan_status["qr_url"])
        self._session.close()
