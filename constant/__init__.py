import os
from json import loads

__all__ = ["KEYRING_SERVICE_NAME", "KEYRING_COOKIES", "KEYRING_SETTINGS",
           "KEYRING_ROOM_INFO", "LOCAL_SERVER_NAME", "VERSION"]

KEYRING_SERVICE_NAME = "StartLive|userCredentials"
KEYRING_COOKIES = "cookies"
KEYRING_SETTINGS = "settings"
KEYRING_ROOM_INFO = "roomInfo"
LOCAL_SERVER_NAME = "StartLive|singleInstanceServer"
VERSION = "0.3.5"

# Might change
_loaded = None


def _load_constants():
    global _loaded
    if _loaded is None:
        try:
            json_path = os.path.join(os.path.dirname(__file__), "resources",
                                     "version.json")
            with open(json_path, "r", encoding="utf-8") as f:
                _loaded = loads(f.read())
        except FileNotFoundError:
            json_path = os.path.join(os.path.dirname(__file__), "..",
                                     "resources", "version.json")
            with open(json_path, "r", encoding="utf-8") as f:
                _loaded = loads(f.read())
    return _loaded


_ver = _load_constants()
APP_KEY = _ver["ak"]
APP_SECRET = _ver["as"]
LIVEHIME_BUILD = _ver["b"]
LIVEHIME_VERSION = _ver["v"]
HEADERS_WEB = _ver["hw"]
HEADERS_APP = _ver["ha"]
START_LIVE_AUTH_CSRF = _ver["start_ac"]
STOP_LIVE_AUTH_CSRF = _ver["stop_ac"]
