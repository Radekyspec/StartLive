from functools import partial
from json import dumps, loads
from queue import Queue
from typing import Optional

from keyring import get_password
from obsws_python import ReqClient
from requests import Session

import constant
from constant import *
from models.classes import ThreadSafeDict

dumps = partial(dumps, ensure_ascii=False,
                separators=(",", ":"))

# Global session for HTTP requests
session = Session()
session.trust_env = False
session.headers.update(constant.HEADERS_WEB)
session.cookies.set("appkey", constant.APP_KEY, domain="bilibili.com", path="/")

# Queue to communicate with OBS in a separate thread
obs_req_queue = Queue()

# Scan status flags for login
scan_status = ThreadSafeDict({
    "scanned": False, "qr_key": None, "qr_url": None,
    "timeout": False, "wait_for_confirm": False,
    "area_updated": False, "room_updated": False,
    "const_updated": False, "announce_updated": False,
})

# Stream status stores fetched RTMP info and verification state
stream_status = ThreadSafeDict({
    "live_status": False,
    "required_face": False,
    "identified_face": False,
    "face_url": None,
    "stream_addr": None,
    "stream_key": None
})

app_settings = ThreadSafeDict({
    "use_proxy": False,
})
if (app := get_password(KEYRING_SERVICE_NAME,
                        KEYRING_APP_SETTINGS)) is not None:
    app_settings.update(loads(app))
    if app_settings["use_proxy"]:
        session.get = partial(session.get, verify=False, timeout=5)
        session.post = partial(session.post, verify=False, timeout=5)
        session.trust_env = True
    else:
        session.get = partial(session.get, verify=True, timeout=5)
        session.post = partial(session.post, verify=True, timeout=5)
        session.trust_env = False

# Managed by models.workers.credential_manager
room_info = ThreadSafeDict({})
obs_settings = ThreadSafeDict({})
usernames = ThreadSafeDict({})

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
