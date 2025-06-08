from functools import partial
from json import dumps
from queue import Queue
from typing import Optional

from obsws_python import ReqClient
from requests import Session

from constant import APP_KEY
from models.classes import ThreadSafeDict


dumps = partial(dumps, ensure_ascii=False,
                separators=(",", ":"))

# Headers used for all requests to simulate a browser environment
headers = {
    "Accept": "*/*",
    "Accept-Encoding": "gzip, deflate",
    "Accept-Language": "zh-CN,zh;q=0.9,en-CN;q=0.8,en;q=0.7",
    "Cache-Control": "no-cache",
    "Dnt": "1",
    "Pragma": "no-cache",
    "Priority": "u=1, i",
    "Origin": "https://live.bilibili.com",
    "Referer": "https://live.bilibili.com/",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/105.0.0.0 Safari/537.36 pc_app/livehime build/8902"
}

# Global session for HTTP requests
session = Session()
session.headers.update(headers)
session.cookies.set("appkey", APP_KEY, domain="bilibili.com", path="/")
session.get = partial(session.get, timeout=5)
session.post = partial(session.post, timeout=5)

# Queue to communicate with OBS in a separate thread
obs_req_queue = Queue()


# Scan status flags for login
scan_status = ThreadSafeDict({
    "scanned": False, "qr_key": None, "qr_url": None,
    "timeout": False, "wait_for_confirm": False,
    "area_updated": False, "room_updated": False
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
