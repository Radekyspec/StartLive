from contextlib import suppress

# module import
from ipaddress import IPv6Address, ip_address
from threading import Condition

# package import
from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QIntValidator
from PySide6.QtWidgets import (
    QAbstractScrollArea,
    QApplication,
    QCheckBox,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

# local package import
from src.core import app_state
from src.core.constant import CoverStatus
from src.core.workers.announce import AnnounceUpdateWorker
from src.core.workers.area import AreaUpdateWorker, FetchRecentAreaWorker
from src.core.workers.cover import FetchCoverWorker
from src.core.workers.live import StartLiveWorker, StopLiveWorker
from src.core.workers.obs_ws import ObsConnectorWorker, ObsDaemonWorker
from src.core.workers.title import TitleUpdateWorker
from src.PySide.classes import CompletionComboBox, FocusAwareLineEdit
from src.PySide.interface_adapters.announce import AnnounceUpdatePresenter
from src.PySide.interface_adapters.area import (
    AreaUpdatePresenter,
    FetchRecentAreaPresenter,
)
from src.PySide.interface_adapters.cover import FetchCoverPresenter
from src.PySide.interface_adapters.live import StartLivePresenter, StopLivePresenter
from src.PySide.interface_adapters.obs_ws import ObsConnectorPresenter
from src.PySide.interface_adapters.title import TitleUpdatePresenter
from src.PySide.states import ObsBtnState, StreamState
from src.PySide.window import AreaPickerPanel, CoverCropWidget


class StreamConfigPanel(QWidget):

    @staticmethod
    def _create_form_label(
        text: str,
        buddy: QWidget,
        accessible_name: str,
    ) -> QLabel:
        label = QLabel(text)
        label.setBuddy(buddy)
        buddy.setAccessibleName(accessible_name)
        return label

    def __init__(self, parent_window, *args, **kwargs):
        super().__init__(parent_window, *args, **kwargs)
        self.parent_window = parent_window
        self.setObjectName("StreamConfigPanel")
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self._cond = Condition()

        self.stream_state = StreamState()
        self.stream_state.addressUpdated.connect(self.fill_stream_info)
        self.stream_state.faceRequired.connect(
            self.parent_window.popup_face_widget)
        self.obs_btn_state = ObsBtnState()
        self.obs_btn_state.obsConnected.connect(self._obs_btn_connected)
        self.obs_btn_state.obsDisconnected.connect(self._obs_btn_disconnected)
        self.obs_btn_state.obsConnecting.connect(self._obs_btn_connecting)
        self.cover_crop_widget: CoverCropWidget | None = None

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        self.scroll_area = QScrollArea(self)
        self.scroll_area.setObjectName("StreamConfigScrollArea")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll_area.setSizeAdjustPolicy(
            QAbstractScrollArea.SizeAdjustPolicy.AdjustIgnored)
        self.scroll_area.setMinimumSize(0, 0)

        self._scroll_content = QWidget()
        self._scroll_content.setObjectName("StreamConfigContent")
        self._scroll_content.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.main_layout = QVBoxLayout(self._scroll_content)
        self.main_layout.setContentsMargins(20, 20, 20, 16)
        self.main_layout.setSpacing(12)
        self.main_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll_area.setWidget(self._scroll_content)
        root_layout.addWidget(self.scroll_area)

        header = QWidget()
        header.setObjectName("StreamHeader")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(2, 0, 2, 0)
        header_layout.setSpacing(2)
        page_title = QLabel("开播控制台")
        page_title.setObjectName("PageTitle")
        page_subtitle = QLabel("管理 OBS 连接、推流信息与直播资料")
        page_subtitle.setObjectName("PageSubtitle")
        header_layout.addWidget(page_title)
        header_layout.addWidget(page_subtitle)
        self.main_layout.addWidget(header)

        def _addr_save():
            app_state.obs_settings["ip_addr"] = self.host_input.text()

        def _port_save():
            app_state.obs_settings["port"] = self.port_input.text()

        def _password_save():
            app_state.obs_settings["password"] = self.pass_input.text()

        def _auto_live_save():
            app_state.obs_settings[
                "auto_live"] = self.obs_auto_live_checkbox.isChecked()

        def _auto_connect_save():
            app_state.obs_settings[
                "auto_connect"] = self.obs_auto_connect_checkbox.isChecked()

        _form_label = self._create_form_label

        # 顶部区域：OBS 连接信息
        obs_group = QGroupBox("OBS 连接设置")
        obs_group.setObjectName("SectionCard")
        obs_layout = QGridLayout()
        obs_layout.setHorizontalSpacing(10)
        obs_layout.setVerticalSpacing(8)

        self.host_input = QLineEdit("localhost")
        self.host_input.editingFinished.connect(_addr_save)
        obs_layout.addWidget(
            _form_label("服务器 IP:", self.host_input, "OBS 服务器地址"), 1, 0)
        obs_layout.addWidget(self.host_input, 1, 1)

        self.port_input = QLineEdit("4455")
        self.port_input.setValidator(QIntValidator(1, 65535, self.port_input))
        self.port_input.editingFinished.connect(_port_save)
        obs_layout.addWidget(
            _form_label("端口:", self.port_input, "OBS WebSocket 端口"), 1, 2)
        obs_layout.addWidget(self.port_input, 1, 3)

        self.pass_input = QLineEdit()
        self.pass_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.pass_input.textEdited.connect(_password_save)
        obs_layout.addWidget(
            _form_label("服务器密码:", self.pass_input, "OBS 服务器密码"), 1, 4)
        obs_layout.addWidget(self.pass_input, 1, 5)

        self.connect_btn = QPushButton("连接")
        self.connect_btn.setObjectName("SecondaryAction")
        self.connect_btn.setAccessibleName("连接或断开 OBS")
        self.connect_btn.clicked.connect(self._connect_obs)
        obs_layout.addWidget(self.connect_btn, 1, 6)
        # self._obs_timer.timeout.connect(self._obs_btn_state)

        obs_hint = QLabel(
            "在 OBS 中打开 WebSocket服务器 功能，在下方填写信息以自动导入推流地址到OBS\n未连接 OBS 时自动推流将不会生效")
        obs_hint.setObjectName("InlineWarning")
        obs_hint.setWordWrap(True)
        obs_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        obs_layout.addWidget(obs_hint, 0, 0, 1, 7)

        obs_auto_start = QFrame()
        obs_auto_start.setObjectName("InlineControls")
        obs_auto_start_layout = QHBoxLayout()
        obs_auto_start_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.obs_auto_live_checkbox = QCheckBox("自动推流")
        self.obs_auto_live_checkbox.setToolTip(
            "勾选此项后，软件内点击开播时会自动点击OBS的推流"
        )
        self.obs_auto_live_checkbox.setChecked(False)
        self.obs_auto_live_checkbox.setEnabled(False)
        self.obs_auto_live_checkbox.checkStateChanged.connect(_auto_live_save)
        obs_auto_start_layout.addWidget(self.obs_auto_live_checkbox)
        self.obs_auto_connect_checkbox = QCheckBox("自动连接OBS")
        self.obs_auto_connect_checkbox.setToolTip(
            "勾选此项后，软件打开时会自动尝试连接OBS"
        )
        self.obs_auto_connect_checkbox.checkStateChanged.connect(
            _auto_connect_save)
        self.obs_auto_connect_checkbox.setChecked(False)
        self.obs_auto_connect_checkbox.setEnabled(True)
        obs_auto_start_layout.addWidget(self.obs_auto_connect_checkbox)

        obs_auto_start.setLayout(obs_auto_start_layout)
        obs_layout.addWidget(obs_auto_start, 2, 0, 1, 7)

        obs_group.setLayout(obs_layout)
        self.main_layout.addWidget(obs_group, stretch=1)

        # 中部区域：推流地址与密钥
        stream_group = QGroupBox("推流信息 (自动生成)")
        stream_group.setObjectName("SectionCard")
        stream_layout = QGridLayout()
        stream_layout.setHorizontalSpacing(10)
        stream_layout.setVerticalSpacing(8)

        self.addr_input = QLineEdit()
        self.addr_input.setReadOnly(True)
        stream_layout.addWidget(
            _form_label("串流地址:", self.addr_input, "串流地址"), 0, 0)
        stream_layout.addWidget(self.addr_input, 0, 1, 1, 6)
        self.copy_addr_btn = QPushButton("复制")
        self.copy_addr_btn.setObjectName("GhostAction")
        self.copy_addr_btn.setAccessibleName("复制串流地址")
        stream_layout.addWidget(self.copy_addr_btn, 0, 8)

        self.key_input = FocusAwareLineEdit()
        self.key_input.setReadOnly(True)
        stream_layout.addWidget(
            _form_label("串流密钥:", self.key_input, "串流密钥"), 1, 0)
        stream_layout.addWidget(self.key_input, 1, 1, 1, 6)
        self.copy_key_btn = QPushButton("复制")
        self.copy_key_btn.setObjectName("GhostAction")
        self.copy_key_btn.setAccessibleName("复制串流密钥")
        stream_layout.addWidget(self.copy_key_btn, 1, 8)

        stream_group.setLayout(stream_layout)
        self.main_layout.addWidget(stream_group, stretch=1)

        # 分区选择
        area_group = QGroupBox("直播信息")
        area_group.setObjectName("SectionCard")
        area_group_layout = QGridLayout()
        area_group_layout.setHorizontalSpacing(10)
        area_group_layout.setVerticalSpacing(8)
        self.title_input = CompletionComboBox([])
        area_group_layout.addWidget(
            _form_label("房间标题:", self.title_input, "房间标题"), 0, 0)
        area_group_layout.addWidget(self.title_input, 0, 1, 1, 6)
        self.save_title_btn = QPushButton("保存")
        self.save_title_btn.setObjectName("GhostAction")
        self.save_title_btn.setAccessibleName("保存房间标题")
        self.save_title_btn.clicked.connect(self._save_title)
        area_group_layout.addWidget(self.save_title_btn, 0, 8)

        self.announce_input = QLineEdit()
        area_group_layout.addWidget(
            _form_label("主播公告:", self.announce_input, "主播公告"), 1, 0)
        area_group_layout.addWidget(self.announce_input, 1, 1, 1, 6)
        self.save_announce_btn = QPushButton("保存")
        self.save_announce_btn.setObjectName("GhostAction")
        self.save_announce_btn.setAccessibleName("保存主播公告")
        self.save_announce_btn.clicked.connect(self._save_announce)
        area_group_layout.addWidget(self.save_announce_btn, 1, 8)

        self.parent_combo = CompletionComboBox(app_state.parent_area)
        self.parent_combo.setAccessibleName("直播父分区")
        area_group_layout.addWidget(
            _form_label("分区选择:", self.parent_combo, "直播父分区"), 2, 0)
        # self.parent_combo.addItems(config.parent_area)
        area_group_layout.addWidget(self.parent_combo, 2, 1, 1, 3)
        self._child_combo_autosave = False
        self.child_combo = CompletionComboBox([])
        self.child_combo.setAccessibleName("直播子分区")
        self.child_combo.setEnabled(False)
        area_group_layout.addWidget(self.child_combo, 2, 4, 1, 3)
        self.modify_area_btn = QPushButton("修改")
        self.modify_area_btn.setObjectName("GhostAction")
        self.modify_area_btn.setAccessibleName("修改直播分区")
        # self.save_area_btn.clicked.connect(self._save_area)
        self.modify_area_btn.clicked.connect(self._open_area_dialog)
        # self.parent_combo.editTextChanged.connect(self._activate_area_save)
        # self.child_combo.editTextChanged.connect(self._activate_area_save)
        self.child_combo.editTextChanged.connect(self._save_area)
        area_group_layout.addWidget(self.modify_area_btn, 2, 8)

        self.cover_status = QLabel("尚未获取")
        self.cover_status.setObjectName("StatusText")
        self.cover_status.setProperty("status", "neutral")
        self.cover_status.setAccessibleName("直播封面审核状态")
        self.cover_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        area_group_layout.addWidget(self.cover_status, 3, 1, 1, 6)
        self.cover_edit_btn = QPushButton("修改")
        self.cover_edit_btn.setObjectName("GhostAction")
        self.cover_edit_btn.setAccessibleName("修改直播封面")
        self.cover_edit_btn.clicked.connect(self._edit_cover)
        area_group_layout.addWidget(
            _form_label("直播封面:", self.cover_edit_btn, "修改直播封面"),
            3, 0)
        area_group_layout.addWidget(self.cover_edit_btn, 3, 8)

        area_group.setLayout(area_group_layout)
        self.main_layout.addWidget(area_group, stretch=1)

        # 底部：控制按钮
        control_layout = QHBoxLayout()
        control_layout.setContentsMargins(4, 4, 4, 0)
        self.start_btn = QPushButton("开始直播")
        self.start_btn.setObjectName("PrimaryAction")
        self.start_btn.setAccessibleName("开始直播")
        self.stop_btn = QPushButton("停止直播")
        self.stop_btn.setObjectName("DangerAction")
        self.stop_btn.setAccessibleName("停止直播")
        self.start_btn.setMinimumHeight(36)
        self.stop_btn.setMinimumHeight(36)
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
        self.start_btn.clicked.connect(self.start_live)
        self.stop_btn.clicked.connect(self.stop_live)

    def reset_obs_settings(self):
        app_state.obs_settings_default()
        self.host_input.setText(app_state.obs_settings["ip_addr"])
        self.port_input.setText(app_state.obs_settings["port"])
        self.pass_input.setText(app_state.obs_settings["password"])
        self.obs_auto_connect_checkbox.setChecked(False)
        self.obs_auto_live_checkbox.setChecked(False)

    def enable_child_combo_autosave(self, enabled: bool) -> bool:
        old = self._child_combo_autosave
        self._child_combo_autosave = enabled
        return old

    def update_child_combo(self, text):
        if text in app_state.area_options:
            _enabled = self.enable_child_combo_autosave(False)
            self.child_combo.clear()
            self.child_combo.addItems(app_state.area_options[text])
            self.child_combo.setEnabled(True)
            self.enable_child_combo_autosave(_enabled)
            self._save_area(self.child_combo.currentText())
        else:
            self.child_combo.clear()
            self.child_combo.setEnabled(False)

    @Slot()
    def _open_area_dialog(self):
        self.modify_area_btn.setEnabled(False)
        dlg = AreaPickerPanel(self,
                              recent_pairs=app_state.room_info["recent_areas"])
        if not app_state.room_info["recent_areas"]:
            self.parent_window.add_thread(
                FetchRecentAreaWorker(FetchRecentAreaPresenter(dlg)))
        # 可选：设置默认选中
        if self._valid_area():
            dlg.set_initial_selection(self.parent_combo.currentText(),
                                      self.child_combo.currentText())

        @Slot()
        def _apply(parent_text, child_text):
            _enabled = self.enable_child_combo_autosave(False)
            self.parent_combo.setCurrentText(parent_text)
            self.enable_child_combo_autosave(_enabled)
            self.child_combo.setCurrentText(child_text)

        dlg.selectionConfirmed.connect(_apply)
        dlg.finished.connect(self._activate_area_save)
        dlg.exec()

    @Slot()
    def _activate_area_save(self):
        self.modify_area_btn.setEnabled(True)

    def copy_address(self):
        QApplication.clipboard().setText(self.addr_input.text())

    def copy_key(self):
        QApplication.clipboard().setText(self.key_input.text())

    @Slot()
    def start_live(self):
        app_state.room_info["recent_areas"].clear()
        self._start_live()

    @Slot()
    def stop_live(self):
        self._stop_live()

    def _start_live(self):
        if not self._valid_area() or not self.start_btn.isEnabled():
            return
        self.start_btn.setEnabled(False)
        self.parent_window.tray_start_live_action.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.parent_window.tray_stop_live_action.setEnabled(True)
        # self.parent_combo.setEnabled(False)
        # self.child_combo.setEnabled(False)
        # self.save_area_btn.setEnabled(False)
        if app_state.obs_settings.get("auto_connect",
                                      False) and app_state.obs_client is None:
            self.connect_btn.click()
        area_code = app_state.area_codes[self.child_combo.currentText()]
        app_state.room_info["parent_area"] = self.parent_combo.currentText()
        app_state.room_info["area"] = self.child_combo.currentText()
        app_state.room_info["area_code"] = area_code
        self.parent_window.add_thread(StartLiveWorker(
            StartLivePresenter(self, self.stream_state, cond=self._cond),
            area=area_code))

    def _stop_live(self):
        if not self.stop_btn.isEnabled():
            return
        self.start_btn.setEnabled(True)
        self.parent_window.tray_start_live_action.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.parent_window.tray_stop_live_action.setEnabled(False)
        # self.parent_combo.setEnabled(True)
        # self.child_combo.setEnabled(True)
        app_state.stream_status["stream_key"] = None
        app_state.stream_status["stream_addr"] = None
        self.addr_input.setText("")
        self.key_input.setText("")
        if (app_state.obs_client is not None
                and self.obs_auto_live_checkbox.isChecked()):
            app_state.obs_req_queue.put(("StopStream", {}))
        self.parent_window.add_thread(StopLiveWorker(StopLivePresenter(self)))

    def fill_stream_info(self, addr: str, key: str):
        if app_state.obs_connecting:
            return
        self.addr_input.setText(
            str(addr))
        self.key_input.setText(
            str(key))

        if app_state.obs_client is not None:
            app_state.obs_req_queue.put(("SetStreamServiceSettings", {
                "streamServiceType": "rtmp_custom",
                "streamServiceSettings": {
                    "bwtest": False,
                    "server": str(addr),
                    "key": str(key),
                    "use_auth": False
                }
            }))
            if self.obs_auto_live_checkbox.isChecked():
                app_state.obs_req_queue.put(("StartStream", {}))

    @Slot()
    def _connect_obs(self):
        if app_state.obs_client is None and not app_state.obs_op:
            obs_host = self.host_input.text()
            try:
                ip_object = ip_address(obs_host)
                if isinstance(ip_object, IPv6Address):
                    obs_host = f"[{obs_host}]"
            except ValueError:
                # Host names require no IPv6 bracket normalization.
                obs_host = str(obs_host)
            connector = ObsConnectorWorker(
                ObsConnectorPresenter(self, self.obs_btn_state, self._cond),
                host=obs_host,
                port=self.port_input.text(),
                password=self.pass_input.text(),
                cond=self._cond
            )
            self.parent_window.add_thread(connector, on_progress=True)
        elif app_state.obs_client is not None and not app_state.obs_op:
            ObsDaemonWorker.disconnect_obs()
            self.obs_btn_state.obsDisconnected.emit()
            self.obs_auto_live_checkbox.setEnabled(False)

    @Slot()
    def _obs_btn_connecting(self):
        self.connect_btn.setText("连接中")

    @Slot()
    def _obs_btn_connected(self):
        self.connect_btn.setText("断开")

    @Slot()
    def _obs_btn_disconnected(self):
        self.connect_btn.setText("连接")

    def _set_cover_status(self, text: str, status: str) -> None:
        self.cover_status.setText(text)
        self.cover_status.setAccessibleDescription(text)
        self.cover_status.setProperty("status", status)
        style = self.cover_status.style()
        style.unpolish(self.cover_status)
        style.polish(self.cover_status)
        self.cover_status.update()

    def cover_audit_state(self):
        if app_state.room_info["cover_status"] == CoverStatus.AUDIT_PASSED:
            self._set_cover_status("审核通过~", "success")
        elif app_state.room_info[
            "cover_status"] == CoverStatus.AUDIT_IN_PROGRESS:
            self._set_cover_status("审核中...可以先行开播喔~", "warning")
        elif app_state.room_info["cover_status"] == CoverStatus.AUDIT_FAILED:
            self._set_cover_status(
                f"审核未通过: {app_state.room_info['cover_audit_reason']}",
                "error")
        else:
            self._set_cover_status("尚未获取", "neutral")

    @Slot()
    def _save_title(self):
        self.save_title_btn.setEnabled(False)
        self.parent_window.add_thread(
            TitleUpdateWorker(TitleUpdatePresenter(self),
                              self.title_input.currentText()))

    @Slot()
    def _edit_cover(self):
        if app_state.room_info["cover_status"] == 0:
            return
        self.cover_edit_btn.setEnabled(False)
        self.cover_crop_widget = CoverCropWidget(self)
        self.cover_crop_widget.destroyed.connect(self._on_cover_exit)
        self.parent_window.add_thread(
            FetchCoverWorker(FetchCoverPresenter(self.cover_crop_widget)))
        self.cover_crop_widget.show()

    @Slot()
    def _on_cover_exit(self):
        self.cover_edit_btn.setEnabled(True)
        cover_crop_widget = self.cover_crop_widget
        if cover_crop_widget is not None:
            with suppress(RuntimeError):
                cover_crop_widget.hide()
            with suppress(RuntimeError):
                cover_crop_widget.deleteLater()
        self.cover_crop_widget = None

    @Slot()
    def _save_announce(self):
        self.save_announce_btn.setEnabled(False)
        self.parent_window.add_thread(
            AnnounceUpdateWorker(AnnounceUpdatePresenter(self),
                                 self.announce_input.text()))

    def _valid_area(self):
        parent_choose = self.parent_combo.currentText()
        if parent_choose == "请选择":
            return False
        return parent_choose in app_state.parent_area and self.child_combo.currentText() in \
            app_state.area_options[self.parent_combo.currentText()]

    @Slot()
    def _save_area(self, child_area: str):
        if self._valid_area() and self._child_combo_autosave:
            # self.save_area_btn.setEnabled(False)
            self.parent_window.add_thread(
                AreaUpdateWorker(AreaUpdatePresenter(self), child_area))
