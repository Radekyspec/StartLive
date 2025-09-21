from functools import partial
from json import dumps, loads
from queue import Queue
from typing import Optional

from keyring import get_password
from obsws_python import ReqClient
from requests import Session
from requests.cookies import cookiejar_from_dict

import constant
from constant import *
from models.classes import ThreadSafeDict

dumps = partial(dumps, ensure_ascii=False,
                separators=(",", ":"))
_APP_CONFIG_INITIALIZATION = {
    "proxy_mode": "none",
    "custom_proxy_url": "",
    "custom_tray_icon": "",
    "custom_tray_hint": "",
    "custom_font": "",
}
_OBS_SETTINGS_INITIALIZATION = {
    "ip_addr": "localhost",
    "port": "4455",
    "password": "",
    "auto_live": False,
    "auto_connect": False
}
_SCAN_STATUS_INITIALIZATION = {
    "scanned": False, "qr_key": None, "qr_url": None,
    "timeout": False, "wait_for_confirm": False,
    "area_updated": False, "room_updated": False,
    "const_updated": True, "announce_updated": False
}
_STREAM_STATUS_INITIALIZATION = {
    "live_status": False,
    "required_face": False,
    "identified_face": False,
    "face_url": None,
    "stream_addr": None,
    "stream_key": None
}
_ROOM_INFO_INITIALIZATION = {
    "cover_audit_reason": "",
    "cover_url": "",
    "cover_status": 0,
    "cover_data": None,
    "room_id": "",
    "title": "",
    "parent_area": "",
    "area": "",
    "announcement": "",
}

# Queue to communicate with OBS in a separate thread
obs_req_queue = Queue()

# Scan status flags for login
scan_status = ThreadSafeDict.new(_SCAN_STATUS_INITIALIZATION)

# Stream status stores fetched RTMP info and verification state
stream_status = ThreadSafeDict.new(_STREAM_STATUS_INITIALIZATION)

app_settings = ThreadSafeDict.new(_APP_CONFIG_INITIALIZATION)

if (app := get_password(KEYRING_SERVICE_NAME,
                        KEYRING_APP_SETTINGS)) is not None:
    app_settings.update(loads(app))

# Managed by models.workers.credential_manager
room_info = ThreadSafeDict({})
obs_settings = ThreadSafeDict({})
usernames = ThreadSafeDict({})
# A cache of cookie indices
cookie_indices = []

# Area (category) selections for live stream configuration
parent_area = ["请选择"]
area_options = {}
area_codes = {}

# OBS WebSocket client
obs_client: Optional[ReqClient] = None
obs_op = False
obs_connecting = False

# Store cookies after login
cookies_dict = {}


def create_session() -> Session:
    session = Session()
    session.headers.update(constant.HEADERS_APP)
    cookiejar_from_dict(cookies_dict,
                        cookiejar=session.cookies)
    session.cookies.set("appkey", constant.APP_KEY, domain="bilibili.com",
                        path="/")
    custom_proxy = app_settings.get("custom_proxy_url", "")
    custom_proxy = {
        "http": custom_proxy,
        "https": custom_proxy,
    }
    match app_settings["proxy_mode"]:
        case "none":
            session.get = partial(session.get, verify=True, timeout=5)
            session.post = partial(session.post, verify=True, timeout=5)
            session.trust_env = False
        case "system":
            session.get = partial(session.get, verify=False, timeout=5)
            session.post = partial(session.post, verify=False, timeout=5)
            session.trust_env = True
        case "custom":
            session.get = partial(session.get, verify=False, timeout=5,
                                  proxies=custom_proxy)
            session.post = partial(session.post, verify=False, timeout=5,
                                   proxies=custom_proxy)
            session.trust_env = False
    return session


def app_settings_default():
    app_settings.update(_APP_CONFIG_INITIALIZATION)


def scan_settings_default():
    scan_status.update(_SCAN_STATUS_INITIALIZATION)


def room_info_default():
    room_info.update(_ROOM_INFO_INITIALIZATION)


def stream_status_default():
    stream_status.update(_STREAM_STATUS_INITIALIZATION)


def obs_settings_default():
    obs_settings.update(_OBS_SETTINGS_INITIALIZATION)
