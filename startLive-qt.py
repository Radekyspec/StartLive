# PySide6 reimplementation of the Bilibili live stream login app
# Replaces tkinter with PySide6 and modern GUI patterns

# module import
import sys
from contextlib import suppress
from functools import partial
from ipaddress import ip_address, IPv6Address
from json import dumps, loads
from queue import Queue, Empty
from threading import Lock
from time import sleep
from typing import Optional

# package import
from darkdetect import isDark
from keyring import get_password, set_password
from obsws_python import ReqClient
from PIL import ImageQt
from PySide6.QtCore import Qt, QTimer, Slot, QThreadPool, Signal
from PySide6.QtGui import QIntValidator, QPixmap
from PySide6.QtWidgets import (QApplication,
                               QCheckBox, QComboBox, QGridLayout, QGroupBox,
                               QHBoxLayout,
                               QLabel, QLineEdit, QMainWindow, QMessageBox,
                               QPushButton,
                               QVBoxLayout, QWidget
                               )
from qdarktheme import setup_theme, enable_hi_dpi
from qrcode import QRCode
from requests import Session
from requests.cookies import cookiejar_from_dict

# local package import
from constant import *
from exceptions import CredentialExpiredError
from models import BaseWorker, LongLiveWorker

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
    "Origin": "https://www.bilibili.com",
    "Referer": "https://www.bilibili.com/",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"
}

# Global session for HTTP requests
session = Session()
session.headers.update(headers)

# Queue to communicate with OBS in a separate thread
obs_req_queue = Queue()


class ThreadSafeDict:
    def __init__(self, value: dict):
        self._dict: dict = value
        self._lock = Lock()

    def __bool__(self):
        return bool(self._dict)

    def __getitem__(self, key):
        return self._dict[key]

    def __setitem__(self, key, value):
        with self._lock:
            self._dict[key] = value

    def __delitem__(self, key):
        with self._lock:
            del self._dict[key]

    def __contains__(self, key):
        with self._lock:
            return key in self._dict

    def get(self, key, default=None):
        with self._lock:
            return self._dict.get(key, default)

    def __repr__(self):
        with self._lock:
            return repr(self._dict)

    def update(self, value, **kwargs):
        with self._lock:
            self._dict.update(value, **kwargs)

    @property
    def internal(self) -> dict:
        return self._dict


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

room_info = ThreadSafeDict({
    "room_id": "",
    "title": ""
})

stream_settings = ThreadSafeDict({})

# Area (category) selections for live stream configuration
parent_area = ["请选择"]
area_options = {}
area_codes = {}

# OBS WebSocket client
obs_client: Optional[ReqClient] = None
obs_op = False

# Store cookies after login
cookies_dict = {}


class ClickableLabel(QLabel):
    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

    def mousePressEvent(self, event):
        self.clicked.emit()


class FocusAwareLineEdit(QLineEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setEchoMode(QLineEdit.Password)  # Start with password mode

    def focusInEvent(self, event):
        super().focusInEvent(event)
        self.setEchoMode(QLineEdit.Normal)  # Reveal text when focused

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self.setEchoMode(QLineEdit.Password)  # Hide text when focus is lost


class CredentialManagerWorker(BaseWorker):
    def __init__(self, parent_window: "MainWindow"):
        super().__init__(name="凭据管理")
        self.parent_window = parent_window

    @Slot()
    def run(self, /) -> None:
        try:
            if (saved_settings := get_password(KEYRING_SERVICE_NAME,
                                               KEYRING_SETTINGS)) is not None:
                stream_settings.update(loads(saved_settings))
            else:
                stream_settings.update({
                    "ip_addr": "localhost",
                    "port": "4455",
                    "password": "",
                    "auto_live": False,
                })
            panel = self.parent_window.panel
            panel.host_input.setText(stream_settings["ip_addr"])
            panel.port_input.setText(stream_settings["port"])
            panel.pass_input.setText(stream_settings["password"])
            panel.obs_auto_start_checkbox.setChecked(
                stream_settings["auto_live"])
            if (saved_cookies := get_password(KEYRING_SERVICE_NAME,
                                              KEYRING_COOKIES)) is not None:
                saved_cookies = loads(saved_cookies)
                cookiejar_from_dict(saved_cookies,
                                    cookiejar=session.cookies)
                nav_url = "https://api.bilibili.com/x/web-interface/nav"
                response = session.get(nav_url).json()
                if response["code"] != 0:
                    raise CredentialExpiredError("登录凭据过期, 请重新登录")
                cookies_dict.update(saved_cookies)
                scan_status["scanned"] = True
                FetchLoginWorker.post_login(self.parent_window)
        except Exception as e:
            self.exception = e
        finally:
            self.finished = True


class QRLoginWorker(BaseWorker):
    def __init__(self, parent_window: "MainWindow"):
        super().__init__(name="登录二维码")
        self.parent_window = parent_window

    @Slot()
    def run(self):
        # logic from run_qr_login()
        generate_url = "https://passport.bilibili.com/x/passport-login/web/qrcode/generate"
        try:
            response = session.get(generate_url).json()
            scan_status["qr_key"] = response["data"]["qrcode_key"]
            scan_status["qr_url"] = response["data"]["url"]
            self.parent_window.update_qr_image(response["data"]["url"])
        except Exception as e:
            self.exception = e
        finally:
            self.finished = True


class StartLiveWorker(BaseWorker):
    def __init__(self, parent_window: "StreamConfigPanel", area):
        super().__init__(name="开播任务")
        self.area = area
        self.parent_window = parent_window

    @Slot()
    def run(self, /) -> None:
        live_url = "https://api.live.bilibili.com/room/v1/Room/startLive"
        try:
            self.fetch_upstream()
            live_data = {
                "room_id": room_info["room_id"],
                "platform": "pc_link",
                "area_v2": self.area,
                "backup_stream": 0,
                "csrf_token": cookies_dict["bili_jct"],
                "csrf": cookies_dict["bili_jct"]
            }
            response = session.post(live_url, data=live_data)
            response = response.json()
            print(response)
            match response["code"]:
                case 0:
                    stream_status["stream_addr"] = response["data"]["rtmp"][
                        "addr"]
                    stream_status["stream_key"] = response["data"]["rtmp"][
                        "code"]
                case 60024:
                    stream_status.update({
                        "required_face": True,
                        "face_url": response["data"]["qr"]
                    })
                case _:
                    raise RuntimeError(response["message"])
        except Exception as e:
            self.parent_window.start_btn.setEnabled(True)
            self.parent_window.stop_btn.setEnabled(False)
            # self.parent_window.parent_combo.setEnabled(True)
            # self.parent_window.child_combo.setEnabled(True)
            self.parent_window.save_area_btn.setEnabled(True)
            self.exception = e
        finally:
            self.finished = True

    @staticmethod
    def fetch_upstream():
        stream_url = "https://api.live.bilibili.com/xlive/app-blink/v1/live/FetchWebUpStreamAddr"
        stream_data = {
            "platform": "pc_link",
            "backup_stream": 0,
            "csrf_token": cookies_dict["bili_jct"],
            "csrf": cookies_dict["bili_jct"]
        }
        response = session.post(stream_url, data=stream_data).json()
        return response["data"]["addr"]["addr"], response["data"]["addr"][
            "code"]


class StopLiveWorker(BaseWorker):
    def __init__(self, parent_window: "StreamConfigPanel"):
        super().__init__(name="停播任务")
        self.parent_window = parent_window

    @Slot()
    def run(self, /) -> None:
        url = "https://api.live.bilibili.com/room/v1/Room/stopLive"
        stop_data = {
            "room_id": room_info["room_id"],
            "platform": "pc_link",
            "csrf_token": cookies_dict["bili_jct"],
            "csrf": cookies_dict["bili_jct"]
        }
        try:
            response = session.post(url, data=stop_data).json()
            if response["code"] != 0:
                raise ValueError(response["message"])
        except Exception as e:
            self.parent_window.start_btn.setEnabled(False)
            self.parent_window.stop_btn.setEnabled(True)
            # self.parent_window.parent_combo.setEnabled(False)
            # self.parent_window.child_combo.setEnabled(False)
            self.parent_window.save_area_btn.setEnabled(True)
            self.exception = e
        finally:
            self.finished = True


class FetchLoginWorker(LongLiveWorker):
    def __init__(self, parent_window: "MainWindow"):
        super().__init__(name="登录")
        self.parent_window = parent_window

    @staticmethod
    def _fetch_area_id():
        url = "https://api.live.bilibili.com/room/v1/Area/getList"
        response = session.get(url).json()
        for area_info in response["data"]:
            parent_area.append(area_info["name"])
            area_options[area_info["name"]] = []
            for sub_area in area_info["list"]:
                area_codes[sub_area["name"]] = sub_area["id"]
                area_options[area_info["name"]].append(sub_area["name"])
        scan_status["area_updated"] = True

    @staticmethod
    def post_login(parent: "MainWindow"):
        parent.add_thread(FetchPreLiveWorker(parent.panel))
        FetchLoginWorker._fetch_area_id()
        set_password(KEYRING_SERVICE_NAME, KEYRING_COOKIES,
                     dumps(cookies_dict))

    @Slot()
    def run(self, /) -> None:
        check_url = "https://passport.bilibili.com/x/passport-login/web/qrcode/poll"
        while scan_status["qr_key"] is None and self._is_running:
            sleep(0.1)
        params = {
            "qrcode_key": scan_status["qr_key"],
            "source": "main-fe-header",
            "web_location": "333.1007"
        }
        try:
            while not scan_status["scanned"] and self._is_running:
                response = session.get(check_url, params=params)
                result = response.json()
                match result["data"]["code"]:
                    case 86101:  # Not scanned yet
                        continue
                    case 86038:  # QR expired
                        scan_status["timeout"] = True
                        break
                    case 86090:  # Scanned but not confirmed
                        scan_status["wait_for_confirm"] = True
                    case 0:  # Login successful
                        global cookies_dict
                        cookies_dict = response.cookies.get_dict()
                        # cookies_dict["refresh_token"] = result["data"][
                        #     "refresh_token"]
                        scan_status["scanned"] = True
                        self.post_login(self.parent_window)
                        break
                    case _:
                        raise RuntimeError(result["message"])
                sleep(2)  # Wait between polls
        except Exception as e:
            self.exception = e
        finally:
            self.finished = True


class FetchPreLiveWorker(BaseWorker):
    def __init__(self, parent_window: "StreamConfigPanel"):
        super().__init__(name="房间信息")
        self.parent_window = parent_window

    def _fetch_pre_live(self):
        info_url = "https://api.live.bilibili.com/xlive/web-ucenter/user/live_info"
        url = "https://api.live.bilibili.com/xlive/app-blink/v1/room/GetInfo"
        response = session.get(info_url).json()
        room_info["room_id"] = response["data"]["room_id"]
        response = session.get(url, params={"platform": "pc"}).json()
        if response["data"]["live_status"] == 1:
            stream_status["live_status"] = True
            addr, code = StartLiveWorker.fetch_upstream()
            self.parent_window.addr_input.setText(addr)
            self.parent_window.key_input.setText(code)
            self.parent_window.parent_combo.setCurrentText(
                response["data"]["parent_name"]
            )
            self.parent_window.child_combo.setCurrentText(
                response["data"]["area_v2_name"]
            )
            self.parent_window.start_btn.setEnabled(False)
            self.parent_window.stop_btn.setEnabled(True)
        scan_status["room_updated"] = True

    @Slot()
    def run(self, /) -> None:
        url = "https://api.live.bilibili.com/xlive/app-blink/v1/preLive/PreLive"
        params = {
            "platform": "web",
            "mobi_app": "web",
            "build": "1",
        }
        try:
            response = session.get(url, params=params).json()
            room_info["title"] = response["data"]["title"]
            self.parent_window.title_input.setText(
                response["data"]["title"])
            self.parent_window.title_input.textEdited.connect(
                lambda: self.parent_window.save_title_btn.setEnabled(True))
            self._fetch_pre_live()
        except Exception as e:
            self.exception = e
        finally:
            self.finished = True


class TitleUpdateWorker(BaseWorker):
    def __init__(self, parent_window: "StreamConfigPanel", title):
        super().__init__(name="标题更新")
        self.parent_window = parent_window
        self.title = title

    @Slot()
    def run(self, /) -> None:
        url = "https://api.live.bilibili.com/room/v1/Room/update"
        title_data = {
            "platform": "pc_link",
            "room_id": room_info["room_id"],
            "title": self.title,
            "csrf_token": cookies_dict["bili_jct"],
            "csrf": cookies_dict["bili_jct"]
        }
        try:
            response = session.post(url, data=title_data).json()
            if response["code"] != 0:
                raise ValueError(response["message"])
        except Exception as e:
            self.exception = e
            self.parent_window.save_title_btn.setEnabled(True)
        finally:
            self.finished = True


class AreaUpdateWorker(BaseWorker):
    def __init__(self, parent_window: "StreamConfigPanel"):
        super().__init__(name="标题更新")
        self.parent_window = parent_window

    @Slot()
    def run(self, /) -> None:
        url = "https://api.live.bilibili.com/xlive/app-blink/v2/room/AnchorChangeRoomArea"
        area_data = {
            "room_id": room_info["room_id"],
            "area_id": area_codes[self.parent_window.child_combo.currentText()],
            "platform": "pc_link",
            "csrf_token": cookies_dict["bili_jct"],
            "csrf": cookies_dict["bili_jct"],
        }
        try:
            response = session.post(url, data=area_data)
            print(response.text)
            response.raise_for_status()
            if (response := response.json())["code"] != 0:
                raise ValueError(response["message"])
        except Exception as e:
            self.exception = e
            self.parent_window.save_area_btn.setEnabled(True)
        finally:
            self.finished = True


class ObsDaemonWorker(LongLiveWorker):
    def __init__(self, parent_window: "StreamConfigPanel",
                 host, port, password):
        super().__init__(name="OBS通讯")
        self.parent_window = parent_window
        self.host = host
        self.port = port
        self.password = password

    @Slot()
    def run(self, /) -> None:
        global obs_client, obs_op
        obs_op = True
        try:
            obs_client = ReqClient(host=self.host, port=self.port,
                                   password=self.password,
                                   timeout=3)
            obs_op = False

        except Exception as e:
            self.exception = e
            obs_op = False
            self.parent_window.obs_auto_start_checkbox.setEnabled(False)
        else:
            self.parent_window.obs_auto_start_checkbox.setEnabled(True)
            while obs_client is not None and self._is_running:
                with suppress(Empty):
                    req, body = obs_req_queue.get(timeout=.2)
                    obs_client.send(req, body)
        finally:
            self.disconnect_obs()
            self.finished = True

    @staticmethod
    def disconnect_obs():
        global obs_op, obs_client
        obs_op = True
        if obs_client is not None:
            obs_client.disconnect()
        obs_client = None
        obs_op = False


class FaceAuthWorker(LongLiveWorker):
    def __init__(self, qr_window: "FaceQRWidget"):
        super().__init__(name="人脸认证")
        self.qr_window = qr_window

    @Slot()
    def run(self, /) -> None:
        try:
            url = "https://api.live.bilibili.com/xlive/app-blink/v1/preLive/IsUserIdentifiedByFaceAuth"
            verify_data = {
                "room_id": room_info["room_id"],
                "face_auth_code": "60024",
                "csrf_token": cookies_dict["bili_jct"],
                "csrf": cookies_dict["bili_jct"],
                "visit_id": "",
            }
            verified = False
            while self._is_running and not verified and self.qr_window:
                response = session.post(url, data=verify_data).json()
                print(response)
                for key in response["data"]:
                    if response["data"][key]:
                        verified = True
                sleep(1)
        except Exception as e:
            self.exception = e
        finally:
            with suppress(RuntimeError):
                self.qr_window.deleteLater()
            self.finished = True


class FaceQRWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("人脸认证")
        self.setWindowFlags(
            Qt.WindowType.Window | Qt.WindowType.WindowCloseButtonHint)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        layout = QVBoxLayout()

        self.face_hint = QLabel("目标分区需要人脸认证")
        self.face_hint.setStyleSheet("color: red; font-size: 16pt;")
        self.face_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.face_qr = QLabel()
        self.face_qr.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.face_hint)
        layout.addWidget(self.face_qr)
        self.setLayout(layout)


class StreamConfigPanel(QWidget):
    def __init__(self, parent_window):
        super().__init__()
        self.parent_window = parent_window

        self._obs_timer = QTimer()
        self.main_layout = QVBoxLayout()
        self.setLayout(self.main_layout)
        self.main_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        def _addr_save():
            stream_settings["ip_addr"] = self.host_input.text()

        def _port_save():
            stream_settings["port"] = self.port_input.text()

        def _password_save():
            stream_settings["password"] = self.pass_input.text()

        def _auto_live_save():
            stream_settings[
                "auto_live"] = self.obs_auto_start_checkbox.isChecked()

        # 顶部区域：OBS 连接信息
        obs_group = QGroupBox("OBS 连接设置")
        obs_layout = QGridLayout()

        obs_layout.addWidget(QLabel("服务器IP:"), 1, 0)
        self.host_input = QLineEdit("localhost")
        self.host_input.editingFinished.connect(_addr_save)
        obs_layout.addWidget(self.host_input, 1, 1)

        obs_layout.addWidget(QLabel("端口:"), 1, 2)
        self.port_input = QLineEdit("4455")
        self.port_input.setValidator(QIntValidator(1, 65535))
        self.port_input.editingFinished.connect(_port_save)
        obs_layout.addWidget(self.port_input, 1, 3)

        obs_layout.addWidget(QLabel("服务器密码:"), 1, 4)
        self.pass_input = QLineEdit()
        self.pass_input.setEchoMode(QLineEdit.Password)
        self.pass_input.editingFinished.connect(_password_save)
        obs_layout.addWidget(self.pass_input, 1, 5)

        self.connect_btn = QPushButton("连接")
        self.connect_btn.clicked.connect(self._connect_obs)
        obs_layout.addWidget(self.connect_btn, 1, 6)
        self._obs_timer.timeout.connect(self._obs_btn_state)

        obs_hint = QLabel(
            "在 OBS 中打开 WebSocket服务器 功能，在下方填写信息以自动导入推流地址到OBS\n未连接 OBS 时自动推流将不会生效")
        obs_hint.setStyleSheet("color: red")
        obs_hint.setWordWrap(True)
        obs_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        obs_layout.addWidget(obs_hint, 0, 0, 1, 7)

        obs_auto_start = QWidget()
        obs_auto_start_layout = QGridLayout()
        obs_auto_start_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.obs_auto_start_checkbox = QCheckBox("自动推流")
        self.obs_auto_start_checkbox.setChecked(False)
        self.obs_auto_start_checkbox.setEnabled(False)
        self.obs_auto_start_checkbox.checkStateChanged.connect(_auto_live_save)
        obs_auto_start_layout.addWidget(self.obs_auto_start_checkbox)

        obs_auto_start.setLayout(obs_auto_start_layout)
        obs_layout.addWidget(obs_auto_start, 2, 0, 1, 7)

        obs_group.setLayout(obs_layout)
        self.main_layout.addWidget(obs_group, stretch=1)

        # 中部区域：推流地址与密钥
        stream_group = QGroupBox("推流信息 (自动生成)")
        stream_layout = QGridLayout()

        stream_layout.addWidget(QLabel("串流地址:"), 0, 0, 1, 1)
        self.addr_input = QLineEdit()
        self.addr_input.setReadOnly(True)
        stream_layout.addWidget(self.addr_input, 0, 1, 1, 6)
        self.copy_addr_btn = QPushButton("复制")
        stream_layout.addWidget(self.copy_addr_btn, 0, 8)

        stream_layout.addWidget(QLabel("串流密钥:"), 1, 0, 1, 1)
        self.key_input = FocusAwareLineEdit()
        self.key_input.setReadOnly(True)
        stream_layout.addWidget(self.key_input, 1, 1, 1, 6)
        self.copy_key_btn = QPushButton("复制")
        stream_layout.addWidget(self.copy_key_btn, 1, 8)

        stream_group.setLayout(stream_layout)
        self.main_layout.addWidget(stream_group, stretch=1)

        # 分区选择
        area_group = QGroupBox("直播信息")
        area_group_layout = QGridLayout()
        area_group_layout.addWidget(QLabel("房间标题:"), 0, 0, 1, 1)
        self.title_input = QLineEdit()
        area_group_layout.addWidget(self.title_input, 0, 1, 1, 6)
        self.save_title_btn = QPushButton("保存")
        self.save_title_btn.setEnabled(False)
        self.save_title_btn.clicked.connect(self._save_title)
        area_group_layout.addWidget(self.save_title_btn, 0, 8)

        area_group_layout.addWidget(QLabel("分区选择:"), 1, 0, 1, 1)
        self.parent_combo = QComboBox()
        self.parent_combo.addItems(parent_area)
        area_group_layout.addWidget(self.parent_combo, 1, 1, 1, 3)

        self.child_combo = QComboBox()
        self.child_combo.setEnabled(False)
        area_group_layout.addWidget(self.child_combo, 1, 4, 1, 3)
        self.save_area_btn = QPushButton("保存")
        self.save_area_btn.setEnabled(False)
        self.save_area_btn.clicked.connect(self._save_area)
        self.parent_combo.activated.connect(self._activate_area_save)
        self.child_combo.activated.connect(self._activate_area_save)
        area_group_layout.addWidget(self.save_area_btn, 1, 8)

        area_group.setLayout(area_group_layout)
        self.main_layout.addWidget(area_group, stretch=1)

        # 底部：控制按钮
        control_layout = QHBoxLayout()
        self.start_btn = QPushButton("开始直播")
        self.stop_btn = QPushButton("停止直播")
        self.stop_btn.setEnabled(False)

        control_layout.addStretch()
        control_layout.addWidget(self.start_btn)
        control_layout.addWidget(self.stop_btn)
        control_layout.addStretch()

        self.main_layout.addLayout(control_layout, stretch=1)

        # 绑定逻辑
        self.parent_combo.currentTextChanged.connect(self.update_child_combo)
        self.copy_addr_btn.clicked.connect(self.copy_address)
        self.copy_key_btn.clicked.connect(self.copy_key)
        self.start_btn.clicked.connect(self._start_live)
        self.stop_btn.clicked.connect(self._stop_live)

    def update_child_combo(self, text):
        if text in area_options:
            self.child_combo.clear()
            self.child_combo.addItems(area_options[text])
            self.child_combo.setEnabled(True)
        else:
            self.child_combo.clear()
            self.child_combo.setEnabled(False)

    def _activate_area_save(self):
        self.save_area_btn.setEnabled(True)

    def copy_address(self):
        QApplication.clipboard().setText(self.addr_input.text())

    def copy_key(self):
        QApplication.clipboard().setText(self.key_input.text())

    def _start_live(self):
        if not self.parent_combo.currentText() or not self.child_combo.currentText():
            return
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        # self.parent_combo.setEnabled(False)
        # self.child_combo.setEnabled(False)
        self.save_area_btn.setEnabled(False)
        area_code = area_codes[self.child_combo.currentText()]
        self.parent_window.add_thread(StartLiveWorker(self, area_code))
        self.parent_window.timer.timeout.connect(
            self.parent_window.fill_stream_info)
        self.parent_window.timer.start(100)

    def _stop_live(self):
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        # self.parent_combo.setEnabled(True)
        # self.child_combo.setEnabled(True)
        stream_status["stream_key"] = None
        stream_status["stream_addr"] = None
        self.addr_input.setText("")
        self.key_input.setText("")
        if obs_client is not None:
            if self.obs_auto_start_checkbox.isChecked():
                obs_req_queue.put(("StopStream", {}))
        self.parent_window.add_thread(StopLiveWorker(self))

    def _connect_obs(self):
        if obs_client is None:
            obs_host = self.host_input.text()
            try:
                ip_object = ip_address(obs_host)
                if isinstance(ip_object, IPv6Address):
                    obs_host = f"[{obs_host}]"
            except ValueError:
                pass
            self.parent_window.add_thread(
                ObsDaemonWorker(self, host=obs_host,
                                port=self.port_input.text(),
                                password=self.pass_input.text()))
        else:
            ObsDaemonWorker.disconnect_obs()
            self.obs_auto_start_checkbox.setEnabled(False)
        self._obs_timer.start(100)

    def _obs_btn_state(self):
        if not obs_op:
            self.connect_btn.setText(
                "断开" if obs_client is not None else "连接")
            self._obs_timer.stop()

    def _save_title(self):
        self.save_title_btn.setEnabled(False)
        self.parent_window.add_thread(
            TitleUpdateWorker(self, self.title_input.text()))

    def _save_area(self):
        self.save_area_btn.setEnabled(False)
        self.parent_window.add_thread(AreaUpdateWorker(self))


# Main GUI window
class MainWindow(QMainWindow):
    _managed_workers: list[BaseWorker | LongLiveWorker]
    _ll_workers: list[LongLiveWorker]

    def __init__(self):
        super().__init__()
        self._base_interval = 200
        self._worker_interval = 200
        self._max_interval = 10000
        self._thread_pool = QThreadPool()
        self._managed_workers = []
        self._worker_timer = QTimer()
        self.timer = QTimer()
        # Long live workers
        self._ll_workers = []
        self.setWindowTitle(f"登录器 {VERSION}")
        self.setGeometry(300, 200, 520, 420)

        # Widgets for login phase
        self.login_label = QLabel("正在获取保存的登录凭证...")
        self.status_label = ClickableLabel("等待登录中...")
        self.qr_label = QLabel()
        self.panel = StreamConfigPanel(self)

        # Styling and alignment
        for label in [self.login_label, self.status_label]:
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setStyleSheet("font-size: 16pt;")

        self.status_label.setStyleSheet("color: blue; font-size: 16pt;")
        self.qr_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Layout
        layout = QVBoxLayout()
        layout.addWidget(self.login_label)
        layout.addWidget(self.qr_label)
        layout.addWidget(self.status_label)

        central = QWidget()
        central.setLayout(layout)
        self.setCentralWidget(central)

        # Start fetching QR and begin polling thread
        self.credential_worker = CredentialManagerWorker(self)
        self.login_worker = None
        self.add_thread(self.credential_worker)
        self.timer.timeout.connect(self.load_credentials)
        self.timer.start(50)

        # monitor worker health
        self._worker_timer.timeout.connect(self._monitor_exception)
        self._worker_timer.start(self._worker_interval)
        self.face_window: Optional[FaceQRWidget] = None

    def fetch_qr(self, retry=False):
        # Start fetching QR and begin polling thread
        scan_status["timeout"] = False
        self.add_thread(QRLoginWorker(self))
        if retry and self.login_worker is not None:
            self.status_label.clicked.disconnect(self.fetch_qr)
            self.login_worker.stop()
        self.login_worker = FetchLoginWorker(self)
        self.add_thread(self.login_worker)
        self.login_label.setText("请使用手机扫码登录：")
        self.status_label.setText("等待扫码中...")
        self.status_label.setStyleSheet("color: blue; font-size: 16pt;")
        # Timer checks the login state and updates UI

    def load_credentials(self):
        if self.credential_worker.finished:
            # stop check
            self.timer.timeout.disconnect(self.load_credentials)
            self.timer.stop()
            self.timer.timeout.connect(self.check_scan_status)
            self.timer.start(100)
            if not scan_status["scanned"]:
                # Needs update credential
                self.fetch_qr()

    def add_thread(self, worker: BaseWorker | LongLiveWorker):
        self._managed_workers.append(worker)
        if isinstance(worker, LongLiveWorker):
            self._ll_workers.append(worker)
        self._thread_pool.start(worker)

    def _monitor_exception(self):
        done = []
        for worker in self._managed_workers:
            if worker.finished:
                done.append(worker)
                if worker.exception is not None:
                    QMessageBox.critical(self, f"{worker.name}线程错误",
                                         repr(worker.exception))
        for dead_worker in done:
            self._managed_workers.remove(dead_worker)
            if dead_worker in self._ll_workers:
                self._ll_workers.remove(dead_worker)

        if self._managed_workers:
            if len(self._managed_workers) == 1 and len(
                    self._ll_workers) == 1 and any(
                    isinstance(item, ObsDaemonWorker) for item in
                    self._managed_workers):
                # Only OBS daemon left, no need to check in high frequency
                if self._worker_interval < self._max_interval:
                    self._worker_interval = int(
                        min(self._worker_interval * 1.025,
                            self._max_interval))
            elif self._worker_interval != self._base_interval:
                self._worker_interval = self._base_interval
            self._worker_timer.setInterval(self._worker_interval)
        else:
            if self._worker_interval < self._max_interval:
                self._worker_interval = int(min(self._worker_interval * 1.025,
                                                self._max_interval))
            self._worker_timer.setInterval(self._worker_interval)
        # print(f"worker interval: {self._worker_interval}")

    def on_exit(self):
        if stream_settings:
            set_password(KEYRING_SERVICE_NAME, KEYRING_SETTINGS,
                         dumps(stream_settings.internal))
        for worker in self._ll_workers:
            worker.stop()

    @staticmethod
    # Helper: Generate QR code image from URL
    def generate_qr_code(data: str):
        qr = QRCode(box_size=4, border=1)
        qr.add_data(data)
        qr.make(fit=True)
        if isDark():
            img = qr.make_image(fill_color="white", back_color="black")
        else:
            img = qr.make_image(fill_color="black", back_color="white")
        return img.convert("RGB")

    @classmethod
    # Helper: Convert a PIL image to QPixmap for display in QLabel
    def qpixmap_from_str(cls, data: str):
        return QPixmap.fromImage(ImageQt.ImageQt(cls.generate_qr_code(data)))

    def update_qr_image(self, qr_url: str):
        self.qr_label.setPixmap(self.qpixmap_from_str(qr_url))  # Show in UI

    def after_login_success(self):
        self.timer.timeout.disconnect(self.check_scan_status)
        self.timer.stop()
        self.panel.parent_combo.clear()
        self.panel.parent_combo.addItems(parent_area)
        self.setCentralWidget(self.panel)

    def check_scan_status(self):
        if scan_status["scanned"]:
            # Login succeeded, ready to switch to main UI
            self.status_label.setText("登录成功！")
            self.status_label.setStyleSheet("color: green; font-size: 16pt;")
            if not scan_status["area_updated"] or \
                    not scan_status["room_updated"]:
                return
            self.after_login_success()
        elif scan_status["timeout"]:
            self.status_label.setText("二维码已失效，点击这里刷新")
            self.status_label.setStyleSheet("color: red; font-size: 16pt;")
            self.status_label.clicked.connect(lambda: self.fetch_qr(True))
            self.timer.timeout.disconnect(self.check_scan_status)
            self.timer.stop()
        elif scan_status["wait_for_confirm"]:
            self.status_label.setText("已扫码，等待确认登录...")

    def fill_stream_info(self):
        if stream_status["stream_key"] is not None and stream_status[
            "stream_addr"] is not None:
            self.panel.addr_input.setText(str(stream_status["stream_addr"]))
            self.panel.key_input.setText(str(stream_status["stream_key"]))
            if obs_client is not None:
                obs_req_queue.put(("SetStreamServiceSettings", {
                    "streamServiceType": "rtmp_custom",
                    "streamServiceSettings": {
                        "bwtest": False,
                        "server": str(stream_status["stream_addr"]),
                        "key": str(stream_status["stream_key"]),
                        "use_auth": False
                    }
                }))
                if self.panel.obs_auto_start_checkbox.isChecked():
                    obs_req_queue.put(("StartStream", {}))
            self.timer.timeout.disconnect(self.fill_stream_info)
            self.timer.stop()
        elif stream_status["required_face"]:
            stream_status["required_face"] = False
            self.panel.start_btn.setEnabled(True)
            self.panel.stop_btn.setEnabled(False)
            self.panel.parent_combo.setEnabled(True)
            self.panel.child_combo.setEnabled(True)
            self.face_window = FaceQRWidget()
            self.face_window.face_qr.setPixmap(self.qpixmap_from_str(
                stream_status["face_url"]
            ))
            auth_worker = FaceAuthWorker(self.face_window)
            self.face_window.destroyed.connect(auth_worker.stop)
            self.add_thread(auth_worker)
            self.face_window.show()


# Entry point
if __name__ == '__main__':
    enable_hi_dpi()
    app = QApplication(sys.argv)
    setup_theme("auto")
    window = MainWindow()
    app.aboutToQuit.connect(window.on_exit)
    window.show()
    sys.exit(app.exec())
