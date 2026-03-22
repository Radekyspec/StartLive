# module import
from typing import Callable

# local package import
from src.core import app_state
# package import
from src.core.constant import HeadersType
from src.core.exceptions import CoverUploadError
from src.core.log import get_logger
from src.core.workers.base import BaseWorker


class CoverUploadWorker(BaseWorker):
    def __init__(self, data: bytes | bytearray | memoryview, *args, **kwargs):
        super().__init__(name="封面上传", headers_type=HeadersType.WEB, *args,
                         **kwargs)
        self.data = data
        self.logger = get_logger(self.__class__.__name__)

    def run(self, report_progress: Callable | None, *args, **kwargs):
        url = "https://api.bilibili.com/x/upload/web/image"
        self.logger.info("CoverUpload Request")
        params = {
            "csrf": app_state.cookies_dict["bili_jct"],
        }
        upload_data = {
            "bucket": (None, "live"),
            "dir": (None, "new_room_cover"),
            "file": ("blob", self.data, "image/png")
        }
        response = self._session.post(url, params=params, files=upload_data)
        self.logger.info("CoverUpload Response")
        response.raise_for_status()
        response = response.json()
        self.logger.info(f"CoverUpload Result: {response}")
        if response["code"] != 0:
            raise CoverUploadError(response["message"])
        self._update_pre_live(response["data"]["location"])

    def _update_pre_live(self, cover_url: str):
        url = "https://api.live.bilibili.com/xlive/app-blink/v1/preLive/UpdatePreLiveInfo"
        self.logger.info("UpdatePreLiveInfo Request")
        data = {
            "platform": "pc_link",
            "mobi_app": "pc_link",
            "build": "1",
            "cover": cover_url,
            "coverVertical": "",
            "liveDirectionType": "1",
            "csrf_token": app_state.cookies_dict["bili_jct"],
            "csrf": app_state.cookies_dict["bili_jct"],
            "visit_id": "",
        }
        response = self._session.post(url, data=data)
        self.logger.info("UpdatePreLiveInfo Response")
        response.raise_for_status()
        response = response.json()
        self.logger.info(f"UpdatePreLiveInfo Result: {response}")
        if response["code"] != 0:
            raise CoverUploadError(response["message"])
        app_state.room_info.update({
            "cover_url": cover_url,
            "cover_audit_reason": response["data"]["audit_info"][
                "audit_title_reason"],
            "cover_status": response["data"]["audit_info"][
                "audit_title_status"],
        })
        self._session.close()
