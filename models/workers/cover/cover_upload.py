# module import
from functools import partial

# package import
from PySide6.QtCore import Slot

# local package import
import app_state
import constant
from exceptions import CoverUploadError
from models.log import get_logger
from models.workers.base import BaseWorker, run_wrapper
from .cover_state_update import CoverStateUpdateWorker


class CoverUploadWorker(BaseWorker):
    def __init__(self, data: bytes | bytearray | memoryview):
        super().__init__(name="封面上传")
        self.data = data
        self.logger = get_logger(self.__class__.__name__)
        self._session.headers.clear()
        self._session.headers.update(constant.HEADERS_WEB)

    @Slot()
    @run_wrapper
    def run(self, /) -> None:
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

    @Slot()
    def on_finished(self, parent_window: "StreamConfigPanel"):
        parent_window.cover_audit_state()
        cover_state_updater = CoverStateUpdateWorker()
        parent_window.parent_window.add_thread(
            cover_state_updater,
            on_finished=partial(
                cover_state_updater.on_finished, parent_window),
        )
        self._session.close()
        if parent_window.cover_crop_widget is not None:
            parent_window.cover_crop_widget.close()

    @staticmethod
    @Slot()
    def on_exception(parent_window: "CoverCropWidget", *args, **kwargs):
        parent_window.btn_upload.setText("保存封面")
        parent_window.btn_upload.setEnabled(True)
