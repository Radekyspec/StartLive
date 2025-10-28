# module import
from functools import partial
from time import sleep

# package import
from PySide6.QtCore import Slot

# local package import
import app_state
import constant
from exceptions import LoginError
from models.log import get_logger
from models.states import LoginState
from models.workers.announce.fetch_announce import FetchAnnounceWorker
from models.workers.area.fetch_area import FetchAreaWorker
from models.workers.base import LongLiveWorker, run_wrapper
from models.workers.pre_live.fetch_pre_live import FetchPreLiveWorker
from models.workers.pre_live.fetch_room_status import FetchRoomStatusWorker
from models.workers.usernames.fetch_usernames import FetchUsernamesWorker


class FetchLoginWorker(LongLiveWorker):
    def __init__(self, state: LoginState):
        super().__init__(name="登录")
        self.state = state
        self.logger = get_logger(self.__class__.__name__)
        self.cookie_key = None
        self._session.headers.clear()
        self._session.headers.update(constant.HEADERS_WEB)

    @staticmethod
    def post_login(parent: "MainWindow", state: LoginState):
        if app_state.scan_status["scanned"]:
            fetch_status = FetchRoomStatusWorker()
            parent.add_thread(
                fetch_status,
                on_finished=fetch_status.on_finished
            )
            fetch_prelive = FetchPreLiveWorker()
            parent.add_thread(
                fetch_prelive,
                on_finished=partial(fetch_prelive.on_finished,
                                    parent.panel, state)
            )
            fetch_announce = FetchAnnounceWorker()
            parent.add_thread(
                fetch_announce,
                on_finished=partial(fetch_announce.on_finished,
                                    parent.panel)
            )
            area_worker = FetchAreaWorker(state)
            parent.add_thread(
                area_worker,
                on_finished=area_worker.on_finished
            )

    @Slot()
    @run_wrapper
    def run(self, /) -> None:
        check_url = "https://passport.bilibili.com/x/passport-login/web/qrcode/poll"
        while app_state.scan_status["qr_key"] is None and self.is_running:
            sleep(0.1)
        params = {
            "qrcode_key": app_state.scan_status["qr_key"],
            "source": "live_pc",
            "web_location": "0.0"
        }
        while not app_state.scan_status["scanned"] and self.is_running:
            self.logger.info("QR poll Request")
            response = self._session.get(check_url, params=params)
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
                    app_state.scan_status["timeout"] = True
                    self.state.qrExpired.emit()
                    break
                case 86090:  # Scanned but not confirmed
                    self.logger.info(f"QR poll Result: {result}")
                    app_state.scan_status["wait_for_confirm"] = True
                    self.state.qrNotConfirmed.emit()
                    sleep(1)
                    continue
                case 0:  # Login successful
                    app_state.cookies_dict.clear()
                    app_state.cookies_dict.update(response.cookies.get_dict())
                    # config.cookies_dict["refresh_token"] = result["data"][
                    #     "refresh_token"]
                    from models.workers.credentials.credential_manager import \
                        CredentialManagerWorker
                    self.cookie_key = CredentialManagerWorker.add_cookie()
                    app_state.scan_status["scanned"] = True
                    self.state.qrScanned.emit()
                    break
                case _:
                    raise LoginError(result["message"])

    @Slot()
    def on_finished(self, parent_window: "MainWindow"):
        if not self.is_running:
            return
        FetchLoginWorker.post_login(parent_window, self.state)
        if self.cookie_key is not None:
            fetch_usernames = FetchUsernamesWorker("")
            parent_window.add_thread(
                fetch_usernames,
                on_finished=fetch_usernames.on_finished
            )
        self._session.close()
