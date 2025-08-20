__all__ = [
    "KEYRING_SERVICE_NAME", "KEYRING_COOKIES", "KEYRING_COOKIES_INDEX",
    "KEYRING_SETTINGS", "KEYRING_ROOM_INFO", "KEYRING_APP_SETTINGS",
    "LOCAL_SERVER_NAME", "LOGGER_NAME", "VERSION"
]

KEYRING_SERVICE_NAME = "StartLive|userCredentials"
KEYRING_COOKIES = "cookies"
KEYRING_COOKIES_INDEX = "cookiesIndex"
KEYRING_SETTINGS = "settings"
KEYRING_APP_SETTINGS = "appSettings"
KEYRING_ROOM_INFO = "roomInfo"
LOCAL_SERVER_NAME = "StartLive|singleInstanceServer"
LOGGER_NAME = "StartLiveLogger"
VERSION = "0.5.6"

APP_KEY = "aae92bc66f3edfab"
APP_SECRET = "af125a0d5279fd576c1b4418a3e8276d"
LIVEHIME_BUILD = "9600"
LIVEHIME_VERSION = "7.24.0.9600"
HEADERS_WEB = {
    "Accept": "*/*",
    "Accept-Encoding": "gzip, deflate",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Connection": "keep-alive",
    "Origin": "https://live.bilibili.com",
    "Referer": "https://live.bilibili.com/",
    "sec-ch-ua": "\"Chromium\";v=\"105\"",
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": "\"Windows\"",
    "Sec-Fetch-Site": "same-site",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Dest": "empty",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/105.0.0.0 Safari/537.36 pc_app/livehime build/9600"
}
HEADERS_APP = {
    "Accept-Encoding": "gzip,deflate",
    "Connection": "keep-alive",
    "User-Agent": "LiveHime/7.24.0.9600 os/Windows pc_app/livehime build/9600 osVer/10.0_x86_64"
}
START_LIVE_AUTH_CSRF = True
STOP_LIVE_AUTH_CSRF = False
