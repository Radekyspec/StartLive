from enum import StrEnum, unique, IntEnum

__all__ = [
    "KEYRING_SERVICE_NAME", "KEYRING_COOKIES", "KEYRING_COOKIES_INDEX",
    "KEYRING_SETTINGS", "KEYRING_ROOM_INFO", "KEYRING_APP_SETTINGS",
    "LOCAL_SERVER_NAME", "LOGGER_NAME", "USERNAME_DISPLAY_TEMPLATE", "VERSION",
    "DARK_CSS", "LIGHT_CSS", "ProxyMode", "PreferProto", "CoverStatus"
]


@unique
class ProxyMode(IntEnum):
    NONE: int = 0
    SYSTEM: int = 1
    CUSTOM: int = 2


@unique
class PreferProto(IntEnum):
    RTMP: int = 0
    SRT: int = 1


@unique
class CoverStatus(IntEnum):
    AUDIT_FAILED: int = -1
    AUDIT_IN_PROGRESS: int = 0
    AUDIT_PASSED: int = 1


KEYRING_SERVICE_NAME = "StartLive|userCredentials"
KEYRING_COOKIES = "cookies"
KEYRING_COOKIES_INDEX = "cookiesIndex"
KEYRING_SETTINGS = "settings"
KEYRING_APP_SETTINGS = "appSettings"
KEYRING_ROOM_INFO = "roomInfo"
LOCAL_SERVER_NAME = "StartLive|singleInstanceServer"
LOGGER_NAME = "StartLiveLogger"
USERNAME_DISPLAY_TEMPLATE = "{}（{}）"
VERSION = "0.6.2"

APP_KEY = "aae92bc66f3edfab"
APP_SECRET = "af125a0d5279fd576c1b4418a3e8276d"
LIVEHIME_BUILD = "9658"
LIVEHIME_VERSION = "7.25.0.9658"
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
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/105.0.0.0 Safari/537.36 pc_app/livehime build/9658"
}
HEADERS_APP = {
    "Accept-Encoding": "gzip,deflate",
    "Connection": "keep-alive",
    "User-Agent": "LiveHime/7.25.0.9658 os/Windows pc_app/livehime build/9658 osVer/10.0_x86_64"
}
START_LIVE_AUTH_CSRF = True
STOP_LIVE_AUTH_CSRF = False

DARK_CSS = """QComboBox {
    background-color: #3C404D;
    border: none;
    border-radius: 4px;
    padding: 2px 1px 2px 2px;
    padding-left: 8px;
    height: 22 + 8 - 4px * 2;
}

QLineEdit, QTextEdit, QPlainTextEdit {
    background-color: #3C404D;
    border: none;
    border-radius: 4px;
    padding: 4px 1px 4px 4px;
    padding-left: 8px;
    border: 1px solid #3C404D;
    height: 22 + 8 - 4px * 2;
}

QLineEdit:hover, QTextEdit:hover, QPlainTextEdit:hover {
    background-color: #3C404D;
    border-color: #5B6273;
}

QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {
    background-color: #3C404D;
    border-color: #284CB8;
}

QDialog, QMainWindow, QStatusBar, QMenuBar, QMenu {
    background-color: #1D1F26;
}

QMenu::icon {
    left: 4px;
}

QMenu::separator {
    background: #3C404D;
    height: 1px;
    margin: 2px 4px;
}

QMenu::item:disabled {
    color: rgb(153, 153, 153);
    background: transparent;
}

QMenuBar::item {
    background-color: transparent;
}

QMenuBar::item:selected {
    background: #284CB8;
}

QMenu::item {
    padding: 4px 4px + 8;
}

QMenu::item {
    padding-right: 20px;
}

QListWidget, QMenu, SceneTree, SourceTree {
    padding: 2px;
}

QMenu::item {
    padding: 4px 4px + 8;
}

QMenu::item {
    padding-right: 20px;
}

QListWidget::item, SourceTreeItem, QMenu::item, SceneTree::item {
    border-radius: 5px;
    color: #FFFFFF;
    border: 1px solid transparent;
}

QMenu::item:selected {
    background-color: #284CB8;
}

QMenu::item:hover, QMenu::item:selected:hover {
    background-color: #476BD7;
    color: #FFFFFF;
}

QMenu::item:focus, QMenu::item:selected:focus {
    border: 1px solid "transparent";
}"""
LIGHT_CSS = """QComboBox {
    margin-top: 1px;
    margin-bottom: 1px;
    background-color: #FFFFFF;
    border-color: #5B6273;
    border-radius: 4px;
    padding: 2px 1px 2px 2px;
    padding-left: 8px;
    border: 1px solid #d3d3d3;
    height: 22 + 8 - 4px * 2;
}

QCheckBox {
    margin-top: 1px;
    margin-bottom: 1px;
}

QLineEdit {
    background-color: #FFFFFF;
    border-color: #5B6273;
    border-radius: 4px;
    padding: 4px 1px 4px 4px;
    padding-left: 8px;
    border: 1px solid #d3d3d3;
    height: 22 + 8 - 4px * 2;
}

QLineEdit:hover {
    background-color: #FFFFFF;
    border-color: #5B6273;
}

QLineEdit:focus {
    background-color: #FFFFFF;
    border-color: #284CB8;
}

QMenuBar {
    background-color: #e5e5e5;
}

QMenu {
    background-color: #e5e5e5;
    padding: 2px;
}

QMenu::icon {
    left: 4px;
}

QMenu::separator {
    background: #FFFFFF;
    height: 1px;
    margin: 2px 4px;
}

QMenu::item:hover {
    background-color: #476BD7;
    color: #000000;
}

QMenu::item:selected:hover {
    background-color: #476BD7;
    color: #000000;
}

QMenu::item:disabled {
    color: rgb(153, 153, 153);
    background: transparent;
}

QMenu::item:focus {
    border: 1px solid "transparent";
}

QMenu::item:selected:focus {
    border: 1px solid "transparent";
}

QMenu::item:selected {
    background-color: #8cb5ff;
}

QMenu::item {
    padding: 4px 4px + 8;
    padding-right: 20px;
    border-radius: 5px;
    color: #000000;
    border: 1px solid transparent;
}

QMenuBar::item:selected {
    background: #8cb5ff;
}

QMenuBar::item {
    background-color: transparent;
}"""
