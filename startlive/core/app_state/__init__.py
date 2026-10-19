import logging
from contextlib import contextmanager
from dataclasses import dataclass, field
from functools import partial
from json import dumps, loads
from pathlib import Path
from platform import node
from queue import Queue
from tempfile import NamedTemporaryFile
from threading import RLock
from typing import Optional, Any, List

from keyring import get_password, set_password, delete_password
from keyring.errors import KeyringError, PasswordDeleteError
from obsws_python import ReqClient
from requests import Session
from requests.cookies import cookiejar_from_dict

from startlive.core.constant.settings import SettingsName, _SETTINGS_FILES, \
    _LEGACY_SETTINGS_KEYS
from startlive.core.credentials.states import AccountSnapshot
from startlive.core.exceptions import TaskCancelled
from startlive.core.obs.states import ObsOutputStatus
from startlive.core.pk.states.encoder import VideoEncodingConfig
from .app_state_base import StateBase
from .observable_state import ObservableState
from .. import constant
from ..cache import get_cache_path
from ..constant import *
from ..sign import gen_buvid

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
    custom_bg_blur_radius: int = 10
    custom_bg_opacity: int = 50
    custom_bg_mode: BackgroundMode = BackgroundMode.COVER
    app_buvid: str = gen_buvid()
    auto_start_live: bool = False


@dataclass(slots=True)
class ObsSettings(StateBase):
    ip_addr: str = "localhost"
    port: str = "4455"
    password: str = ""
    auto_live: bool = False
    auto_connect: bool = False


@dataclass(slots=True)
class PkEncoderSettings(StateBase):
    config: VideoEncodingConfig = field(default_factory=VideoEncodingConfig)


@dataclass(slots=True)
class PkEncoderRuntime(ObservableState):
    backend: str = ""
    sent_bitrate_bps: int | None = None
    fallback_reason: str = ""


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
    face_voucher: Optional[str] = None
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


@dataclass(slots=True)
class CookieState(StateBase):
    current_cookie_idx: int = 0

    @property
    def cookie_index_len(self) -> int:
        return len(cookie_indices)

    def is_exhausted(self) -> bool:
        return self.current_cookie_idx >= self.cookie_index_len

    def move_to_end(self) -> None:
        self.current_cookie_idx = self.cookie_index_len


# Queue to communicate with OBS in a separate thread
obs_req_queue = Queue()

# Immutable local OBS observation, separate from cached platform stream data.
obs_output_status = ObsOutputStatus()

# Scan status flags for login
scan_status = ScanStatus()

# Stream status stores fetched RTMP info and verification state
stream_status = StreamStatus()

app_settings = AppSettings()

# Only the four editable video preferences are persisted.
pk_encoder_settings = PkEncoderSettings()
pk_encoder_runtime = PkEncoderRuntime()
# Managed by models.workers.credential_manager
room_info = RoomInfo()
obs_settings = ObsSettings()

_SETTINGS_STATES = {
    SettingsName.APP: app_settings,
    SettingsName.OBS: obs_settings,
    SettingsName.PK_ENCODER: pk_encoder_settings,
}
_settings_logger = logging.getLogger(__name__)


def _write_settings(name: SettingsName, values):
    filename = _SETTINGS_FILES[name]
    directory, path = get_cache_path(CacheType.CONFIG, filename)
    # Replace in the same directory so interrupted saves preserve the old file.
    temporary = None
    try:
        with NamedTemporaryFile(mode="w", encoding="utf-8", dir=directory,
                                prefix=filename + ".", suffix=".tmp",
                                delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(dumps(values))
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _delete_keyring_settings(name: SettingsName):
    key = _LEGACY_SETTINGS_KEYS.get(name)
    if key is None:
        return
    try:
        delete_password(KEYRING_SERVICE_NAME, key)
    except PasswordDeleteError:
        pass


def save_settings(name: SettingsName) -> None:
    """Save app, obs or pk_encoder preferences; credentials stay in keyring."""
    state = _SETTINGS_STATES[name]
    values = (pk_encoder_settings["config"].preferences()
              if name == SettingsName.PK_ENCODER else state.as_dict())
    if name == SettingsName.OBS:
        # Reuse the legacy item for the credential alone, never write it to disk.
        password = values.pop("password")
    _write_settings(name, values)
    if name == SettingsName.OBS:
        # Only trim the legacy record after its non-secret fields are on disk.
        set_password(KEYRING_SERVICE_NAME, KEYRING_SETTINGS,
                     dumps({"password": password}))


def delete_settings(name: SettingsName) -> None:
    """Delete stored preferences (and OBS credential) and reset their state."""
    filename = _SETTINGS_FILES[name]
    # Remove legacy first so deleting a file cannot resurrect old preferences.
    _delete_keyring_settings(name)
    _, path = get_cache_path(CacheType.CONFIG, filename, is_makedir=False)
    path.unlink(missing_ok=True)
    _SETTINGS_STATES[name].reset()


def _load_settings(name: SettingsName):
    filename = _SETTINGS_FILES[name]
    _, path = get_cache_path(CacheType.CONFIG, filename, is_makedir=False)
    legacy = False
    try:
        try:
            raw = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            legacy_key = _LEGACY_SETTINGS_KEYS.get(name)
            if legacy_key is None:
                return
            raw = get_password(KEYRING_SERVICE_NAME, legacy_key)
            legacy = raw is not None
        if raw is None:
            return
        values = loads(raw)
        if not isinstance(values, dict):
            raise ValueError("settings must be a JSON object")
        if name == SettingsName.PK_ENCODER:
            pk_encoder_settings.update(
                config=VideoEncodingConfig.from_preferences(values))
        else:
            if name == SettingsName.OBS:
                credential = get_password(KEYRING_SERVICE_NAME,
                                          KEYRING_SETTINGS)
                credential_values = loads(credential) if credential else {}
                if not isinstance(credential_values, dict):
                    raise ValueError("OBS credential must be a JSON object")
                values["password"] = credential_values.get("password", "")
            state = _SETTINGS_STATES[name]
            state.update(
                {key: values[key] for key in state.keys() if key in values})
    except (OSError, UnicodeError, ValueError, TypeError, KeyError,
            KeyringError):
        _settings_logger.warning("Could not load %s settings", name,
                                 exc_info=True)
        return
    if legacy:
        try:
            save_settings(name)
            if name != SettingsName.OBS:
                _delete_keyring_settings(name)
        except (OSError, KeyringError):
            _settings_logger.warning("Could not migrate %s settings", name,
                                     exc_info=True)


for _settings_name in _SETTINGS_FILES:
    _load_settings(_settings_name)

usernames = {}
# A cache of cookie indices
cookie_indices = []
cookie_state = CookieState()
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
account_lock = RLock()
_account_generation = 0


def capture_account_context() -> tuple[int, dict[str, str]]:
    """Capture a login generation and its cookies before starting asynchronous work."""
    with account_lock:
        return _account_generation, dict(cookies_dict)


def account_is_current(generation: int) -> bool:
    with account_lock:
        return generation == _account_generation


@contextmanager
def account_guard(generation: int):
    """Check and publish together; callers must keep network I/O outside this guard."""
    with account_lock:
        if generation != _account_generation:
            raise TaskCancelled()
        yield


def account_snapshot() -> AccountSnapshot:
    with account_lock:
        return AccountSnapshot.capture(cookies_dict, room_info["room_id"])


def replace_account_cookies(cookies: dict[str, str]) -> None:
    """Publish new credentials with an empty room and retire previous async work."""
    global _account_generation
    with account_lock:
        values = dict(cookies)
        _account_generation += 1
        room_info.reset()
        cookies_dict.clear()
        cookies_dict.update(values)


def create_session(h_type: HeadersType, *,
                   inherit_account_cookies: bool = True,
                   account_cookies: dict[str, str] | None = None) -> Session:
    session = Session()
    if h_type == HeadersType.WEB:
        session.headers.update(constant.HEADERS_WEB)
    elif h_type == HeadersType.APP:
        session.headers.update(constant.HEADERS_APP)
    session.cookies.set("appkey", constant.APP_KEY, domain="bilibili.com",
                        path="/")
    session.cookies.set("device_name", node().encode('utf-8').decode('latin-1'),
                        domain="bilibili.com", path="/")
    session.cookies.set("device_platform", constant.DEVICE_PLATFORM,
                        domain="bilibili.com", path="/")
    session.cookies.set("buvid3", app_settings.app_buvid)
    if account_cookies is not None or inherit_account_cookies:
        if account_cookies is None:
            _, account_cookies = capture_account_context()
        cookiejar_from_dict(account_cookies, cookiejar=session.cookies,
                            overwrite=True)
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
    app_settings["custom_bg_blur_radius"] = 10
    app_settings["custom_bg_opacity"] = 50
    app_settings["custom_bg_mode"] = BackgroundMode.COVER


def scan_settings_default() -> None:
    scan_status.reset()
    scan_status["const_updated"] = True


def room_info_default() -> None:
    with account_lock:
        room_info.reset()


def stream_status_default() -> None:
    stream_status.reset()


def obs_settings_default() -> None:
    obs_settings.reset()
