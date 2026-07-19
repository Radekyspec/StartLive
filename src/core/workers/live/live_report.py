from datetime import datetime
from typing import Callable

from src.PySide.log import get_logger
from src.core import app_state
from src.core import constant
from src.core.sign import livehime_sign, order_payload
from src.core.workers.base import BaseWorker


class ReportLiveDataWorker(BaseWorker):
    def __init__(self):
        super().__init__(name="ReportData")
        self.logger = get_logger(self.__class__.__name__)

    def run(self, report_progress: Callable | None, *args, **kwargs):
        url = "https://api.live.bilibili.com/xlive/app-blink/v1/report/ReportData"
        params = livehime_sign({})
        params.update({
            "csrf": app_state.cookies_dict["bili_jct"],
            "csrf_token": app_state.cookies_dict["bili_jct"]
        })
        params = order_payload(params)
        report_data = {
            "broad_type": "0",
            "cover": app_state.room_info.cover_url,
            "ctime": datetime.now().strftime("%Y/%m/%d %H:%M:%S"),
            "definition": "{\"code_rate\":\"3000\",\"frame_rate\":\"60\",\"resolution_ratio\":\"1920x1080\"}",
            "is_obs": "0",
            "is_simple": "1",
            "platform": "pc_link",
            "ruid": app_state.cookies_dict["DedeUserID"],
            "screen_status": "1",
            "title": app_state.room_info.title,
            "type_status": "1",
            "version": constant.LIVEHIME_VERSION
        }
        self.logger.info(f"report data: {report_data}")
        self.logger.info("ReportData Request")
        response = self._session.post(url, params=params, data=report_data)
        self.logger.info("ReportData Response")
        response.encoding = "utf-8"
        self.logger.info(response.text)
