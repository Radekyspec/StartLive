# module import

from typing import Callable
from urllib.parse import quote

# local package import
from src.core import app_state
from src.core.exceptions import StartLiveError
# package import
from src.core.log import get_logger
from src.core.sign import RiskCaptchaCodec
from src.core.workers.base import Presenter, BaseWorker


class FaceCaptchaWorker(BaseWorker):
    def __init__(self, presenter: Presenter, /):
        super().__init__(name="人脸认证v2", presenter=presenter)
        self._codec = RiskCaptchaCodec()
        self.logger = get_logger(self.__class__.__name__)

    def run(self, report_progress: Callable | None, *args, **kwargs) -> None:
        if app_state.stream_status.face_voucher is None:
            return
        reg_url = "https://api.bilibili.com/x/gaia-vgate/v2/register"
        risk_params = {
            "v_voucher": app_state.stream_status.face_voucher,
            "dm_track": "[]",
            "csrf": app_state.cookies_dict["bili_jct"]
        }
        self.logger.info("face v2 register Request")
        response = self._session.post(reg_url, data=risk_params)
        self.logger.info("face v2 register Response")
        response.encoding = "utf-8"
        risk_data_enc = response.json()["data"]["content"]
        content = self._codec.__risk_captcha_dec__(
            app_state.stream_status.face_voucher,
            risk_data_enc
        )
        print(content)
        app_state.stream_status.face_voucher = content["token"]
        match (risk_type := content["type"]):
            case "realname":
                qr_base = "https://www.bilibili.com/h5/risk-control/realname?t="
                t = quote(quote(self._codec.__risk_captcha_enc__({})["token"]))
                app_state.stream_status.face_url = qr_base + t
            case _:
                raise StartLiveError(f"不支持的验证类型: {risk_type}")
