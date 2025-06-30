from functools import partial
from json import dumps
from queue import Queue
from typing import Optional

from obsws_python import ReqClient
from requests import Session

import constant
from models.classes import ThreadSafeDict

dumps = partial(dumps, ensure_ascii=False,
                separators=(",", ":"))

# Global session for HTTP requests
session = Session()
session.headers.update(constant.HEADERS_WEB)
session.cookies.set("appkey", constant.APP_KEY, domain="bilibili.com", path="/")
session.get = partial(session.get, timeout=5)
session.post = partial(session.post, timeout=5)

# Queue to communicate with OBS in a separate thread
obs_req_queue = Queue()


# Scan status flags for login
scan_status = ThreadSafeDict({
    "scanned": False, "qr_key": None, "qr_url": None,
    "timeout": False, "wait_for_confirm": False,
    "area_updated": False, "room_updated": False,
    "const_updated": False
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

# Managed by models.workers.credential_manager
room_info = ThreadSafeDict({})
stream_settings = ThreadSafeDict({})

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
