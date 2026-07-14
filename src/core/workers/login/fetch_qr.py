# module import
from time import time_ns
from typing import Callable

# local package import
from src.core import app_state
from src.core.constant import HeadersType
from src.core.log import get_logger
from src.core.workers.base import BaseWorker, Presenter


class FetchQRWorker(BaseWorker):
    def __init__(self, presenter: Presenter):
        super().__init__(name="登录二维码", headers_type=HeadersType.WEB,
                         presenter=presenter)
        self.logger = get_logger(self.__class__.__name__)

    def run(self, report_progress: Callable | None, *args, **kwargs):
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
