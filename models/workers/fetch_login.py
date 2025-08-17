# module import
from functools import partial
from time import sleep

# package import
from PySide6.QtCore import Slot

# local package import
import config
from exceptions import LoginError
from models.log import get_logger
from models.workers.base import LongLiveWorker, run_wrapper
from .fetch_announce import FetchAnnounceWorker
from .fetch_area import FetchAreaWorker
from .fetch_pre_live import FetchPreLiveWorker
from ..states import LoginState


class FetchLoginWorker(LongLiveWorker):
    def __init__(self, state: LoginState):
        super().__init__(name="登录")
        self.state = state
        self.logger = get_logger(self.__class__.__name__)

    @staticmethod
    def post_login(parent: "MainWindow", state: LoginState):
        if config.scan_status["scanned"]:
            parent.add_thread(
                FetchPreLiveWorker(),
                on_finished=partial(FetchPreLiveWorker.on_finished,
                                    parent.panel, state)
            )
            parent.add_thread(
                FetchAnnounceWorker(),
                on_finished=partial(FetchAnnounceWorker.on_finished,
                                    parent.panel)
            )
            parent.add_thread(
                FetchAreaWorker(state)
            )

    @Slot()
    @run_wrapper
    def run(self, /) -> None:
        check_url = "https://passport.bilibili.com/x/passport-login/web/qrcode/poll"
        while config.scan_status["qr_key"] is None and self.is_running:
            sleep(0.1)
        params = {
            "qrcode_key": config.scan_status["qr_key"],
            "source": "live_pc",
            "web_location": "0.0"
        }
        while not config.scan_status["scanned"] and self.is_running:
            self.logger.info("QR poll Request")
            response = config.session.get(check_url, params=params)
            response.encoding = "utf-8"
            self.logger.info("QR poll Response")
            result = response.json()
            match result["data"]["code"]:
                case 86101:  # Not scanned yet
                    self.logger.info(f"QR poll Result: {result}")
                    sleep(1)
                    continue
                case 86038:  # QR expired
                    self.logger.info(f"QR poll Result: {result}")
                    config.scan_status["timeout"] = True
                    self.state.qrExpired.emit()
                    break
                case 86090:  # Scanned but not confirmed
                    self.logger.info(f"QR poll Result: {result}")
                    config.scan_status["wait_for_confirm"] = True
                    self.state.qrNotConfirmed.emit()
                    sleep(1)
                    continue
                case 0:  # Login successful
                    config.cookies_dict = response.cookies.get_dict()
                    # config.cookies_dict["refresh_token"] = result["data"][
                    #     "refresh_token"]
                    from .credential_manager import CredentialManagerWorker
                    CredentialManagerWorker.add_cookie()
                    config.scan_status["scanned"] = True
                    self.state.qrScanned.emit()
                    break
                case _:
                    raise LoginError(result["message"])

    @Slot()
    def on_finished(self, parent_window: "MainWindow"):
        if not self.is_running:
            return
        FetchLoginWorker.post_login(parent_window, self.state)
