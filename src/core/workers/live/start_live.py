from typing import Callable
from warnings import warn

from src.core import app_state, constant
from src.core.constant import PreferProto, FaceAuthType
from src.core.exceptions import StartLiveError
from src.core.log import get_logger
from src.core.sign import livehime_sign, order_payload
from src.core.workers.base import BaseWorker, Presenter


class StartLiveWorker(BaseWorker):
    def __init__(self, presenter: Presenter, /, area):
        super().__init__(name="开播任务", presenter=presenter)
        self.area = area

    def run(self, report_progress: Callable | None, *args, **kwargs):

        return self.start_live(self._session, self.area)

    @classmethod
    def start_live(cls, session, area) -> int | None:
        logger = get_logger(cls.__name__)
        live_url = "https://api.live.bilibili.com/room/v1/Room/startLive"
        # self.fetch_upstream()
        if constant.START_LIVE_AUTH_CSRF:
            logger.info("startLive sign with csrf")
            live_data = livehime_sign({
                "area_v2": area,
                "csrf_token": app_state.cookies_dict["bili_jct"],
                "csrf": app_state.cookies_dict["bili_jct"],
                "room_id": app_state.room_info["room_id"],
                "type": 2,
            })
        else:
            logger.info("startLive sign without csrf")
            live_data = livehime_sign({
                "room_id": app_state.room_info["room_id"],
                "area_v2": area,
                "type": 2,
            })
            live_data.update({
                "csrf_token": app_state.cookies_dict["bili_jct"],
                "csrf": app_state.cookies_dict["bili_jct"]
            })
            live_data = order_payload(live_data)
        logger.info(f"startLive Request")
        response = session.post(live_url, data=live_data)
        response.encoding = "utf-8"
        logger.info("startLive Response")
        response = response.json()
        match response["code"]:
            case 0:
                result = cls.parse_live_addr(response)
                match result:
                    case 0:
                        return 0
                    case 1:
                        logger.warning(
                            "startLive Response no srt fallback to RTMP")
                        return 1
                    case -1:
                        logger.warning(
                            "startLive Response no srt")
                        return -1
            case FaceAuthType.V1:
                logger.warning(f"startLive Response face auth: {response}")
                app_state.stream_status.update({
                    "required_face": True,
                    "face_url": response["data"]["qr"],
                    "face_message": response["message"]
                })
                return FaceAuthType.V1
            case FaceAuthType.V2:
                # face_auth v2 using v_voucher
                app_state.stream_status.update({
                    "required_face": True,
                    "face_voucher": response["data"]["risk_extra"]["v_voucher"],
                    "face_message": response["message"]
                })
                return FaceAuthType.V2
            case _:
                logger.error(f"startLive Response error: {response}")
                raise StartLiveError(response["message"])

    @staticmethod
    def parse_live_addr(response):
        prefer_proto = app_state.app_settings.get("prefer_proto",
                                                  PreferProto.RTMP)
        srt_protos = [d for d in response["data"]["protocols"] if
                      "srt" == d.get("protocol", "").casefold() and d.get(
                          "addr", "") and d.get("code", "")]
        match prefer_proto:
            case PreferProto.RTMP:
                app_state.stream_status.update({
                    "stream_addr": response["data"]["rtmp"]["addr"],
                    "stream_key": response["data"]["rtmp"]["code"]
                })
                return 0
            case PreferProto.SRT_FALLBACK_RTMP:
                if srt_protos:
                    app_state.stream_status.update({
                        "stream_addr": srt_protos[0]["addr"],
                        "stream_key": srt_protos[0]["code"]
                    })
                    return 0
                else:
                    app_state.stream_status.update({
                        "stream_addr": response["data"]["rtmp"]["addr"],
                        "stream_key": response["data"]["rtmp"]["code"]
                    })
                    return 1
            case PreferProto.SRT_ONLY:
                if srt_protos:
                    app_state.stream_status.update({
                        "stream_addr": srt_protos[0]["addr"],
                        "stream_key": srt_protos[0]["code"]
                    })
                    return 0
                else:
                    return -1
            case _:
                raise ValueError(f"Invalid prefer_proto: {prefer_proto}")

    def fetch_upstream(self):
        warn("fetch_upstream is deprecated", DeprecationWarning)
        stream_url = "https://api.live.bilibili.com/xlive/app-blink/v1/live/FetchWebUpStreamAddr"
        stream_data = livehime_sign({
            "backup_stream": 0,
        })
        stream_data.update({
            "csrf_token": app_state.cookies_dict["bili_jct"],
            "csrf": app_state.cookies_dict["bili_jct"]
        })
        stream_data = order_payload(stream_data)
        response = self._session.post(stream_url, data=stream_data)
        response.encoding = "utf-8"
        response = response.json()
        return response["data"]["addr"]["addr"], response["data"]["addr"][
            "code"]
