# module import
from time import sleep
from typing import Callable

# local package import
from src.core import app_state
# package import
from src.core.constant import HeadersType, LoginResult
from src.core.exceptions import LoginError
from src.core.log import get_logger
from src.core.workers.base import LongLiveWorker, Presenter
from src.core.workers.credentials import CredentialManagerWorker


class FetchLoginWorker(LongLiveWorker):
    def __init__(self, presenter: Presenter):
        super().__init__(name="登录", headers_type=HeadersType.WEB,
                         presenter=presenter)
        self.logger = get_logger(self.__class__.__name__)

    def run(self, report_progress: Callable | None, *args, **kwargs):

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
                    return LoginResult.QR_EXPIRED
                case 86090:  # Scanned but not confirmed
                    self.logger.info(f"QR poll Result: {result}")
                    app_state.scan_status["wait_for_confirm"] = True
                    report_progress(LoginResult.QR_NOT_CONFIRMED)
                    sleep(1)
                    continue
                case 0:  # Login successful
                    app_state.cookies_dict.clear()
                    app_state.cookies_dict.update(
                        response.cookies.get_dict())
                    # config.cookies_dict["refresh_token"] = result["data"][
                    #     "refresh_token"]

                    CredentialManagerWorker.add_cookie()
                    app_state.scan_status["scanned"] = True
                    return LoginResult.SUCCESS
                case _:
                    raise LoginError(result["message"])
        return LoginResult.CANCELLED
