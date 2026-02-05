from dataclasses import dataclass, field
from functools import partial
from json import dumps, loads
from platform import node
from queue import Queue
from typing import Optional, Any, List

from keyring import get_password
from obsws_python import ReqClient
from requests import Session
from requests.cookies import cookiejar_from_dict

import constant
from constant import *
from constant import HeadersType
from sign import gen_buvid
from .app_state_base import StateBase

dumps = partial(dumps, ensure_ascii=False,
                separators=(",", ":"))


@dataclass(slots=True)
class AppSettings(StateBase):
    proxy_mode: ProxyMode = ProxyMode.NONE
    custom_proxy_url: str = ""
    custom_tray_icon: str = ""
    custom_tray_hint: str = ""
    custom_font: str = ""
    prefer_proto: PreferProto = PreferProto.RTMP
    custom_bg: str = ""
    custom_bg_blur_radius: float = 10.0
    custom_bg_opacity: float = 50.0
    custom_bg_mode: BackgroundMode = BackgroundMode.COVER
    app_buvid: str = gen_buvid()


@dataclass(slots=True)
class ObsSettings(StateBase):
    ip_addr: str = "localhost"
    port: str = "4455"
    password: str = ""
    auto_live: bool = False
    auto_connect: bool = False


@dataclass(slots=True)
class ScanStatus(StateBase):
    scanned: bool = False
    qr_key: Optional[str] = None
    qr_url: Optional[str] = None
    expired: bool = False
    is_new: bool = False
    cred_loaded: bool = False
    timeout: bool = False
    wait_for_confirm: bool = False
    area_updated: bool = False
    room_updated: bool = False
    const_updated: bool = False
    announce_updated: bool = False


@dataclass(slots=True)
class StreamStatus(StateBase):
    live_status: bool = False
    required_face: bool = False
    identified_face: bool = False
    face_url: Optional[str] = None
    face_message: Optional[str] = None
    stream_addr: Optional[str] = None
    stream_key: Optional[str] = None


@dataclass(slots=True)
class RoomInfo(StateBase):
    cover_audit_reason: str = ""
    cover_url: str = ""
    cover_status: CoverStatus = CoverStatus.AUDIT_IN_PROGRESS
    cover_data: Any = None
    room_id: str = ""
    title: str = ""
    parent_area: str = ""
    area: str = ""
    area_code: int = 0
    announcement: str = ""
    recent_areas: List[str] = field(default_factory=list)
    recent_title: List[str] = field(default_factory=list)


# Queue to communicate with OBS in a separate thread
obs_req_queue = Queue()

# Scan status flags for login
scan_status = ScanStatus()

# Stream status stores fetched RTMP info and verification state
stream_status = StreamStatus()

app_settings = AppSettings()

if (app := get_password(KEYRING_SERVICE_NAME,
                        KEYRING_APP_SETTINGS)) is not None:
    app_settings.update(loads(app))

# Managed by models.workers.credential_manager
room_info = RoomInfo()
obs_settings = ObsSettings()
usernames = {}
# A cache of cookie indices
cookie_indices = []

# Area (category) selections for live stream configuration
parent_area = ["请选择"]
area_options: dict[str, List[str]] = {}
area_reverse: dict[str, str] = {}
area_codes = {}

# OBS WebSocket client
obs_client: Optional[ReqClient] = None
obs_op = False
obs_connecting = False

# Store cookies after login
cookies_dict = {}


def create_session(h_type: HeadersType) -> Session:
    session = Session()
    if h_type == HeadersType.WEB:
        session.headers.update(constant.HEADERS_WEB)
    elif h_type == HeadersType.APP:
        session.headers.update(constant.HEADERS_APP)
    session.cookies.set("appkey", constant.APP_KEY, domain="bilibili.com",
                        path="/")
    session.cookies.set("device_name", node().encode('utf-8').decode('latin-1'),
                        domain="bilibili.com", path="/")
    session.cookies.set("device_platform", "Windows Version: 10.0 x86_64",
                        domain="bilibili.com", path="/")
    session.cookies.set("buvid3", app_settings.app_buvid)
    cookiejar_from_dict(cookies_dict, cookiejar=session.cookies, overwrite=True)
    session.headers.update({
        "buvid": app_settings.app_buvid,
    })
    custom_proxy = app_settings.get("custom_proxy_url", "")
    custom_proxy = {
        "http": custom_proxy,
        "https": custom_proxy,
    }
    match app_settings["proxy_mode"]:
        case ProxyMode.NONE:
            session.get = partial(session.get, verify=True, timeout=5)
            session.post = partial(session.post, verify=True, timeout=5)
            session.trust_env = False
        case ProxyMode.SYSTEM:
            session.get = partial(session.get, verify=False, timeout=5)
            session.post = partial(session.post, verify=False, timeout=5)
            session.trust_env = True
        case ProxyMode.CUSTOM:
            session.get = partial(session.get, verify=False, timeout=5,
                                  proxies=custom_proxy)
            session.post = partial(session.post, verify=False, timeout=5,
                                   proxies=custom_proxy)
            session.trust_env = False
    return session


def app_settings_default() -> None:
    app_settings.reset()


def bg_settings_default() -> None:
    app_settings["custom_bg"] = ""
    app_settings["custom_bg_blur_radius"] = 10.0
    app_settings["custom_bg_opacity"] = 10.0
    app_settings["custom_bg_mode"] = BackgroundMode.COVER


def scan_settings_default() -> None:
    scan_status.reset()
    scan_status["const_updated"] = True


def room_info_default() -> None:
    room_info.recent_areas.clear()
    room_info.recent_title.clear()
    room_info.reset()


def stream_status_default() -> None:
    stream_status.reset()


def obs_settings_default() -> None:
    obs_settings.reset()
