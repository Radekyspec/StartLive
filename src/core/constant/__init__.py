from enum import IntEnum, StrEnum, unique

from ._version import __version__

__all__ = [
    "KEYRING_SERVICE_NAME", "KEYRING_COOKIES", "KEYRING_COOKIES_INDEX",
    "KEYRING_SETTINGS", "KEYRING_ROOM_INFO", "KEYRING_APP_SETTINGS",
    "LOCAL_SERVER_NAME", "LOGGER_NAME", "USERNAME_DISPLAY_TEMPLATE",
    "MAX_RECENT_TITLE", "VERSION", "DARK_COVER_CSS", "DARK_CSS",
    "DARK_MODERN_CSS", "LIGHT_COVER_CSS", "LIGHT_CSS", "LIGHT_MODERN_CSS",
    "ProxyMode", "PreferProto", "CoverStatus",
    "WidgetIndex", "CacheType", "BackgroundMode", "HeadersType", "LoginResult",
    "FaceAuthType"
]


@unique
class ProxyMode(IntEnum):
    NONE = 0
    SYSTEM = 1
    CUSTOM = 2


@unique
class PreferProto(IntEnum):
    RTMP = 0
    SRT_FALLBACK_RTMP = 1
    SRT_ONLY = 2


@unique
class CoverStatus(IntEnum):
    AUDIT_FAILED = -1
    AUDIT_IN_PROGRESS = 0
    AUDIT_PASSED = 1


@unique
class WidgetIndex(IntEnum):
    WIDGET_LOGIN = 0
    WIDGET_PANEL = 1
    WIDGET_LOGGING = 2
    WIDGET_SETTINGS = 3


@unique
class CacheType(StrEnum):
    LOGS = "logs"
    CONFIG = "config"


@unique
class BackgroundMode(IntEnum):
    NO_SCALE = 0  # 无拉伸
    STRETCH = 1  # 等比拉伸
    FIT = 2  # 等比填充
    COVER = 3  # 等比适应


@unique
class HeadersType(IntEnum):
    WEB = 0
    APP = 1


@unique
class LoginResult(IntEnum):
    CANCELLED = -1
    SUCCESS = 0
    QR_EXPIRED = 86038
    QR_NOT_CONFIRMED = 86090


@unique
class FaceAuthType(IntEnum):
    V1 = 60024
    V2 = 60043


KEYRING_SERVICE_NAME = "StartLive|userCredentials"
KEYRING_COOKIES = "cookies"
KEYRING_COOKIES_INDEX = "cookiesIndex"
KEYRING_SETTINGS = "settings"
KEYRING_APP_SETTINGS = "appSettings"
KEYRING_ROOM_INFO = "roomInfo"
LOCAL_SERVER_NAME = "StartLive|singleInstanceServer"
LOGGER_NAME = "StartLiveLogger"
USERNAME_DISPLAY_TEMPLATE = "{}（{}）"
MAX_RECENT_TITLE = 5
VERSION = __version__

APP_KEY = "aae92bc66f3edfab"
# Public LiveHime client signing constant; not a user or deployment secret.
APP_SECRET = "".join(("af125a0d5279fd57", "6c1b4418a3e8276d"))
LIVEHIME_BUILD = "10783"
LIVEHIME_VERSION = "7.63.0.10783"
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
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/105.0.0.0 Safari/537.36 pc_app/livehime build/10783"
}
HEADERS_APP = {
    "Accept-Encoding": "gzip,deflate",
    "Connection": "keep-alive",
    "User-Agent": "LiveHime/7.63.0.10783 os/Windows pc_app/livehime build/10783 osVer/10.0_x86_64"
}
START_LIVE_AUTH_CSRF = True
STOP_LIVE_AUTH_CSRF = False

DARK_COVER_CSS = """QWidget {
    background: transparent;
}

QComboBox {
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
    padding-left: 10px;
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

QDialog, QMainWindow, QStatusBar, QMenuBar {
    background-color: #1D1F26;
    background: transparent;
}

QMenu {
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
    padding-left: 10px;
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
LIGHT_COVER_CSS = """QWidget {
    background: transparent;
}

QComboBox {
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
    padding-left: 10px;
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
    background: transparent;
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
    padding-left: 10px;
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


DARK_MODERN_CSS = """/* Modern StartLive console: dark */
QWidget#StreamConfigPanel,
QWidget#StreamConfigContent,
QScrollArea#StreamConfigScrollArea,
QScrollArea#StreamConfigScrollArea > QWidget > QWidget {
    background-color: transparent;
}

QScrollArea#StreamConfigScrollArea {
    border: none;
}

QFrame#SideBar {
    background-color: #1b2130;
    border: none;
    border-right: 1px solid #30394b;
}

QGroupBox#SectionCard {
    background-color: #232938;
    border: 1px solid #353e52;
    border-radius: 12px;
    margin-top: 12px;
    padding: 18px 12px 12px 12px;
}

QGroupBox#SectionCard::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
    color: #f1f5ff;
    background-color: #232938;
    font-weight: 600;
}

QLabel#PageTitle {
    color: #f8fafc;
    font-size: 20px;
    font-weight: 700;
}

QLabel#PageSubtitle {
    color: #94a3b8;
    font-size: 11px;
}

QLabel#InlineWarning {
    color: #ffd38c;
    background-color: #3b3024;
    border-radius: 6px;
    padding: 6px;
}

QFrame#InlineControls {
    background-color: #1d2433;
    border-radius: 8px;
}

QLabel#StatusText[status="neutral"] { color: #cbd5e1; }
QLabel#StatusText[status="success"] { color: #86efac; }
QLabel#StatusText[status="warning"] { color: #fde047; }
QLabel#StatusText[status="error"] { color: #fda4af; }

QLineEdit:focus, QComboBox:focus {
    border: 2px solid #afc3ff;
}

QPushButton#PrimaryAction {
    background-color: #4052a8;
    border: 1px solid #7184dd;
    border-radius: 8px;
    color: #ffffff;
    font-weight: 600;
    padding: 7px 18px;
}

QPushButton#PrimaryAction:hover { background-color: #4a5dbc; }
QPushButton#PrimaryAction:pressed { background-color: #34448d; }
QPushButton#PrimaryAction:focus {
    background-color: #34448d;
    border: 2px solid #ffffff;
}

QPushButton#DangerAction {
    background-color: #3a2530;
    border: 1px solid #a65b73;
    border-radius: 8px;
    color: #ffc3cf;
    padding: 7px 18px;
}

QPushButton#DangerAction:hover { background-color: #4b2d3b; }
QPushButton#DangerAction:focus { border: 2px solid #ffe08a; }

QPushButton#GhostAction, QPushButton#SecondaryAction {
    background-color: #2b3345;
    border: 1px solid #52607d;
    border-radius: 7px;
    color: #e2e8f0;
    padding: 6px 13px;
}

QPushButton#GhostAction:hover, QPushButton#SecondaryAction:hover {
    background-color: #343e5a;
    border-color: #8798e8;
}

QPushButton#GhostAction:focus, QPushButton#SecondaryAction:focus {
    background-color: #343e5a;
    border: 2px solid #afc3ff;
}

QToolButton#MenuButton {
    border: 1px solid transparent;
    border-radius: 8px;
    color: #cbd5e1;
    padding: 6px;
}

QToolButton#MenuButton:hover { background-color: #2c354b; }
QToolButton#MenuButton:checked {
    background-color: #3a4568;
    color: #ffffff;
}
QToolButton#MenuButton:focus {
    background-color: #2c354b;
    border: 2px solid #afc3ff;
}
"""

LIGHT_MODERN_CSS = """/* Modern StartLive console: light */
QWidget#StreamConfigPanel,
QWidget#StreamConfigContent,
QScrollArea#StreamConfigScrollArea,
QScrollArea#StreamConfigScrollArea > QWidget > QWidget {
    background-color: transparent;
}

QScrollArea#StreamConfigScrollArea {
    border: none;
}

QFrame#SideBar {
    background-color: #f8fafc;
    border: none;
    border-right: 1px solid #d8e0eb;
}

QGroupBox#SectionCard {
    background-color: #ffffff;
    border: 1px solid #d8e0eb;
    border-radius: 12px;
    margin-top: 12px;
    padding: 18px 12px 12px 12px;
}

QGroupBox#SectionCard::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
    color: #1e293b;
    background-color: #ffffff;
    font-weight: 600;
}

QLabel#PageTitle {
    color: #172033;
    font-size: 20px;
    font-weight: 700;
}

QLabel#PageSubtitle {
    color: #64748b;
    font-size: 11px;
}

QLabel#InlineWarning {
    color: #92400e;
    background-color: #fff7ed;
    border-radius: 6px;
    padding: 6px;
}

QFrame#InlineControls {
    background-color: #f1f5f9;
    border-radius: 8px;
}

QLabel#StatusText[status="neutral"] { color: #475569; }
QLabel#StatusText[status="success"] { color: #166534; }
QLabel#StatusText[status="warning"] { color: #92400e; }
QLabel#StatusText[status="error"] { color: #b91c1c; }

QLineEdit:focus, QComboBox:focus {
    border: 2px solid #172033;
}

QPushButton#PrimaryAction {
    background-color: #4052a8;
    border: 1px solid #33458f;
    border-radius: 8px;
    color: #ffffff;
    font-weight: 600;
    padding: 7px 18px;
}

QPushButton#PrimaryAction:hover { background-color: #354799; }
QPushButton#PrimaryAction:pressed { background-color: #2e3e86; }
QPushButton#PrimaryAction:focus {
    background-color: #354799;
    border: 2px solid #0f172a;
}

QPushButton#DangerAction {
    background-color: #fff1f2;
    border: 1px solid #d98797;
    border-radius: 8px;
    color: #9f2941;
    padding: 7px 18px;
}

QPushButton#DangerAction:hover { background-color: #ffe4e8; }
QPushButton#DangerAction:focus { border: 2px solid #172033; }

QPushButton#GhostAction, QPushButton#SecondaryAction {
    background-color: #f8fafc;
    border: 1px solid #b8c4d4;
    border-radius: 7px;
    color: #334155;
    padding: 6px 13px;
}

QPushButton#GhostAction:hover, QPushButton#SecondaryAction:hover {
    background-color: #eef2ff;
    border-color: #6575c8;
}

QPushButton#GhostAction:focus, QPushButton#SecondaryAction:focus {
    background-color: #eef2ff;
    border: 2px solid #172033;
}

QToolButton#MenuButton {
    border: 1px solid transparent;
    border-radius: 8px;
    color: #475569;
    padding: 6px;
}

QToolButton#MenuButton:hover { background-color: #e8edff; }
QToolButton#MenuButton:checked {
    background-color: #dbe4ff;
    color: #283a99;
}
QToolButton#MenuButton:focus {
    background-color: #e8edff;
    border: 2px solid #172033;
}
"""

DARK_CSS += "\n" + DARK_MODERN_CSS
DARK_COVER_CSS += "\n" + DARK_MODERN_CSS
LIGHT_CSS += "\n" + LIGHT_MODERN_CSS
LIGHT_COVER_CSS += "\n" + LIGHT_MODERN_CSS
