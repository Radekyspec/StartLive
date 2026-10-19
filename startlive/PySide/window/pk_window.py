from PySide6.QtCore import QSignalBlocker, QTimer, Qt, Signal, Slot
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QWidget,
    QVBoxLayout,
    QMessageBox,
)

from startlive.PySide.interface_adapters.gui_dispatcher import GUIDispatcher
from startlive.PySide.interface_adapters.pk.pk_presenter import PkPresenter
from startlive.core.constant.pk import PkMode
from startlive.core.constant.pk_info import NativePkState
from startlive.core.constant.ui import PK_WINDOW_FONT_SIZE_OFFSET_PT
from startlive.core.exceptions import PkError
from startlive.core.pk.identity import current_identity
from startlive.core.pk.states.display import PkRoundDisplay
from startlive.core.pk.states.session import PkOptions
from startlive.core.pk.trace import pk_trace
from startlive.core.workers.worker_manager import WorkerManager


class PkWindow(QDialog):
    """PK controls with OBS capture enabled only in video mode."""
    FONT_SIZE_OFFSET_PT = PK_WINDOW_FONT_SIZE_OFFSET_PT

    startRequested = Signal(object)
    stopRequested = Signal()
    disconnectRequested = Signal()
    continuousChanged = Signal(bool)

    def __init__(self, parent=None, *, session_factory=None,
                 identity_provider=None, provider_preflight=None):
        super().__init__(parent)
        self._apply_font_offset()
        self.setWindowTitle("PK")
        self.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint, False)
        self.setSizeGripEnabled(False)
        self._dispatcher = GUIDispatcher()
        # OBS, RTC, push and HTTP ACK remain alive alongside short API tasks.
        self._workers = WorkerManager(self._dispatcher, max_workers=6)
        self._preview_worker = None
        self._classic_audio = False
        self._preview_owner = object()
        self._candidate_dialog = None
        self._candidate_start = None
        self._search_listener = None
        self._pending_start = None
        self._invitation_reception = None  # No server-setting value is inferred here.
        self._invitation_reception_by_mode = {}
        self._invitation_reception_identity = None
        self._settings_dialog = self._settings_controller = None
        self._encoder_dialog = None
        self._continuous_editable = True
        self._invitation_dialog = None
        self._invitation_waiting = False
        self._preview_future = None
        self._preview_retry = None
        self._shutdown = False
        self._session = None
        self._session_factory = session_factory
        self.provider_readiness = None
        self._provider_preflight = provider_preflight
        self._identity_provider = identity_provider or (
            lambda: current_identity())
        if session_factory is not None:
            self.startRequested.connect(self._start_session)
            self.stopRequested.connect(
                lambda: self._session_action("stop_round"))
            self.disconnectRequested.connect(
                lambda: self._session_action("disconnect"))
            self.continuousChanged.connect(self._change_continuous)
        QApplication.instance().aboutToQuit.connect(self.shutdown)
        self._session_enabled = False
        self._active = False
        self._connection_active = False
        self._publisher_available = {}
        self._publisher_mute_states = {}
        self._publisher_controls = {}
        self.local_view = self.remote_view = self.crop_selector = None
        self.local_buffer = self.remote_buffer = self.publish_buffer = None
        self.audio_timer = self._media_timer = None
        self._video_hint = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 0)
        layout.setSpacing(8)
        controls = QHBoxLayout()
        self.mode = QComboBox()
        self.mode.addItem("经典 PK", PkMode.TRADITIONAL)
        self.mode.addItem("视频 PK", PkMode.VIDEO)
        self.mode.addItem("视频连线", PkMode.VIDEO_LINK)
        self.peer_search = QLineEdit()
        self.peer_search.setPlaceholderText("主播名称 / 房间号")
        self.random_match = QCheckBox("随机 PK")
        self.random_match.setChecked(True)
        self.peer_search.setEnabled(False)
        self.random_match.toggled.connect(self._refresh_match_options)
        self.mode.currentIndexChanged.connect(self._refresh_match_options)
        self.mode.currentIndexChanged.connect(
            lambda _: self._trace("ui.mode_selected"))
        self.random_match.clicked.connect(
            lambda checked: self._trace("ui.match_mode_selected",
                                        random=checked))
        self.continuous = QCheckBox("连续 PK")
        self.continuous.toggled.connect(self.continuousChanged)
        self.start_button = QPushButton("开始 PK")
        self.wait_invitation_button = QPushButton("监听邀请")
        self.wait_invitation_button.setToolTip(
            "监听邀请时仍可输入直播间号或开始随机 PK；接收偏好可在设置中修改")
        self.settings_button = QPushButton("PK / 连线设置")
        self.settings_button.clicked.connect(self._open_settings)
        self.stop_button = QPushButton("结束 PK")
        self.disconnect_button = QPushButton("断开连线")
        self.convert_pk_button = QPushButton("转为 PK")
        self.convert_pk_button.clicked.connect(
            lambda: self._session_action("start_connection_pk"))
        self.start_button.clicked.connect(self._request_start)
        self.wait_invitation_button.clicked.connect(
            self._request_invitation_wait)
        self.stop_button.clicked.connect(self.stopRequested)
        self.disconnect_button.clicked.connect(self.disconnectRequested)
        control_height = max(32, self.fontMetrics().height() + 12)
        self.mode.setFixedSize(120, max(control_height + 6,
                                        self.mode.fontMetrics().height() + 16))
        self.peer_search.setFixedSize(220, control_height)
        controls.setSpacing(10)
        for widget in (self.mode, self.random_match, self.peer_search,
                       self.continuous, self.start_button, self.stop_button):
            controls.addWidget(widget)
        controls.addStretch()
        self.encoder_settings_button = QPushButton("视频编码设置")
        self.encoder_settings_button.setToolTip(
            "独立设置 PK 输出编码方式，不更改 OBS 正常直播")
        self.encoder_settings_button.clicked.connect(
            self._open_encoder_settings)
        layout.addLayout(controls)
        actions = QHBoxLayout()
        actions.setSpacing(8)
        actions.addWidget(self.wait_invitation_button)
        actions.addWidget(self.disconnect_button)
        actions.addWidget(self.convert_pk_button)
        actions.addStretch()
        actions.addWidget(self.settings_button)
        actions.addWidget(self.encoder_settings_button)
        layout.addLayout(actions)
        for button in self.findChildren(QPushButton):
            button.setAutoDefault(False)
            width = 128 if button in (self.settings_button,
                                      self.encoder_settings_button) else 104
            button.setFixedSize(max(width,
                                    button.fontMetrics().horizontalAdvance(
                                        button.text()) + 24),
                                control_height)
            policy = button.sizePolicy()
            policy.setRetainSizeWhenHidden(False)
            button.setSizePolicy(policy)
        self._refresh_match_options()
        self.round_info = QLabel()
        self.round_info.setTextFormat(Qt.TextFormat.PlainText)
        self.round_info.setWordWrap(True)
        self.round_info.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.round_info.hide()
        details = QWidget()
        details_layout = QHBoxLayout(details)
        details_layout.setContentsMargins(10, 8, 10, 8)
        details_layout.setSpacing(16)
        messages = QVBoxLayout()
        messages.setSpacing(4)
        messages.setAlignment(Qt.AlignmentFlag.AlignTop)
        details_layout.addLayout(messages, 1)
        details_layout.addWidget(self.round_info, 1)
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.status.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        messages.addWidget(self.status)
        self.output_status = QLabel()
        self.output_status.setWordWrap(True)
        self.output_status.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.output_status.setToolTip(
            "来自 OBS 当前推流状态，以及采集插件最近收到的画面和声音")
        self.output_status.setTextFormat(Qt.TextFormat.PlainText)
        messages.addWidget(self.output_status)
        self._messages = messages
        details_scroll = QScrollArea()
        details_scroll.setWidgetResizable(True)
        details_scroll.setWidget(details)
        details_scroll.setMinimumHeight(
            max(80, self.fontMetrics().lineSpacing() * 3 + 26))
        details_scroll.setSizePolicy(QSizePolicy.Policy.Expanding,
                                     QSizePolicy.Policy.Ignored)
        layout.addWidget(details_scroll, 1)
        self.set_session_available(session_factory is not None,
                                   "选择 PK 模式后开始，或等待对方邀请。")
        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.setInterval(250)
        self.timer.timeout.connect(self._refresh_state)
        self.timer.start()
        self.mode.currentIndexChanged.connect(self._update_video_mode)
        self._update_video_mode()
        self._trace("ui.window_created")

    def _ensure_video_ui(self):
        if self.local_view is not None:
            return
        from startlive.PySide.interface_adapters.pk.provider_readiness import \
            VideoProviderReadiness
        from startlive.PySide.widgets.pk_crop_selector import PkCropSelector
        from startlive.PySide.widgets.pk_media_view import PkMediaView
        from startlive.core.pk.media_buffer import MediaBuffer
        from startlive.core.pk.states.mute import RtcMuteState

        self.provider_readiness = VideoProviderReadiness(
            self._workers, self._provider_preflight)
        self._publisher_available = {"audio": False, "video": False}
        self._publisher_mute_states = {media: RtcMuteState() for media in
                                       ("audio", "video")}
        self.local_buffer, self.remote_buffer = MediaBuffer(), MediaBuffer()
        self.publish_buffer = MediaBuffer()
        control_height = max(32, self.fontMetrics().height() + 12)
        views = QHBoxLayout()
        views.setSpacing(12)
        self.local_view = PkMediaView(self, title="我的 OBS 画面")
        self.remote_view = PkMediaView(self, title="对方画面")
        self.remote_view.set_muted(False)
        self.local_view.set_crop(self.publish_buffer.video_crop)
        self.crop_selector = PkCropSelector(self)
        self.crop_selector.thumbnail.set_crop(self.publish_buffer.video_crop)
        self.local_view.imageChanged.connect(
            self.crop_selector.thumbnail.set_image)
        self.crop_selector.cropChanged.connect(self._set_video_crop)
        views.addWidget(self.local_view, 0, Qt.AlignmentFlag.AlignTop)
        views.addWidget(self.remote_view, 0, Qt.AlignmentFlag.AlignTop)
        self.layout().insertLayout(2, views)
        audio_controls = QHBoxLayout()
        self.crop_button = QPushButton("画面截取")
        self.crop_button.setAutoDefault(False)
        self.crop_button.setFixedSize(104, control_height)
        self.crop_button.clicked.connect(
            lambda: self.crop_selector.show_above(self.crop_button))
        audio_controls.addWidget(self.crop_button)
        self.local_monitor = QCheckBox("监听本机声音")
        self.local_monitor.toggled.connect(
            lambda checked: self.local_view.set_muted(not checked))
        self.remote_mute = QCheckBox("静音对方")
        self.remote_mute.clicked.connect(
            lambda checked: self._request_remote_mute("audio", checked))
        self.remote_video_mute = QCheckBox("隐藏对方画面")
        self.remote_video_mute.clicked.connect(
            lambda checked: self._request_remote_mute("video", checked))
        audio_controls.addWidget(self.local_monitor)
        self.publisher_audio_mute = QCheckBox("静音我的声音")
        self.publisher_video_mute = QCheckBox("隐藏我的画面")
        self._publisher_controls = {"audio": self.publisher_audio_mute,
                                    "video": self.publisher_video_mute}
        for media, control in self._publisher_controls.items():
            control.setToolTip(
                "仅影响发送给 PK 对方的内容，不改变 OBS 推流或本地预览")
            control.clicked.connect(
                lambda checked, kind=media: self._request_publisher_mute(kind,
                                                                         checked))
            audio_controls.addWidget(control)
            policy = control.sizePolicy()
            policy.setRetainSizeWhenHidden(True)
            control.setSizePolicy(policy)
        audio_controls.addStretch()
        self.local_view.layout().addLayout(audio_controls)
        remote_controls = QHBoxLayout()
        remote_controls.addWidget(self.remote_mute)
        remote_controls.addWidget(self.remote_video_mute)
        remote_controls.addStretch()
        remote_controls.setContentsMargins(0, 0, 0, 0)
        self.remote_mute.setMinimumHeight(control_height)
        self.remote_view.layout().addLayout(remote_controls)
        hint = QLabel(
            "请在 OBS 的工具菜单启动 StartLive PK 采集。使用耳机，并避免在发送音轨中采集对方声音。")
        hint.setWordWrap(True)
        self._video_hint = hint
        hint.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self._messages.addWidget(hint)
        self._preview_retry = QTimer(self)
        self._preview_retry.setSingleShot(True)
        self._preview_retry.setInterval(2000)
        self._preview_retry.timeout.connect(self._start_preview)
        self.audio_timer = QTimer(self)
        self.audio_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.audio_timer.setInterval(10)
        self.audio_timer.timeout.connect(self._refresh_audio)
        self._media_timer = QTimer(self)
        self._media_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._media_timer.setInterval(33)
        self._media_timer.timeout.connect(self._refresh_media)
        self._refresh_publisher_controls()

    def prepare_classic_audio(self):
        """Allocate playback/capture only for an admitted classic JOIN."""
        self._ensure_video_ui()
        self._classic_audio = True
        for view in (self.local_view, self.remote_view):
            view.video.hide()
            view.show()
        for widget in (self.crop_button, self.publisher_video_mute,
                       self.remote_video_mute):
            widget.hide()
        self._video_hint.show()
        self._start_classic_capture()
        self._fit_to_screen()

    def _start_classic_capture(self):
        if not self._classic_audio or self._shutdown or self._preview_worker is not None:
            return
        from startlive.core.workers.pk.obs_media import ObsMediaWorker
        worker = ObsMediaWorker(PkPresenter(
            finished=lambda: self._preview_stopped(worker),
            failed=lambda error: self._preview_failed(error, worker)),
            (self.local_buffer, self.publish_buffer), video=False)
        self._preview_worker = worker
        self.audio_timer.start()
        self._preview_future = self._workers.submit(worker)

    def stop_classic_audio(self):
        if self._classic_audio:
            self._classic_audio = False
            self._stop_preview()

    def _request_remote_mute(self, media, muted):
        if self.mode.currentData() == PkMode.VIDEO:
            if media == "audio":
                self.remote_view.set_muted(muted)
            return
        self._session_action("set_remote_muted", media, muted)

    def set_remote_mute_state(self, *, audio, video):
        with QSignalBlocker(self.remote_mute), QSignalBlocker(
                self.remote_video_mute):
            self.remote_mute.setChecked(audio)
            self.remote_video_mute.setChecked(video)
        self.remote_view.set_muted(audio)
        self.remote_view.video.setVisible(not video and not self._classic_audio)

    @Slot(QFont)
    def _apply_font_offset(self):
        font = QApplication.font()
        if (font_size_f := font.pointSizeF()) > 0:
            font.setPointSizeF(font_size_f + self.FONT_SIZE_OFFSET_PT)
            font_size = f"{font.pointSizeF():g}pt"
        else:
            offset_px = round(
                self.FONT_SIZE_OFFSET_PT * self.logicalDpiY() / 72)
            font.setPixelSize(font.pixelSize() + offset_px)
            font_size = f"{font.pixelSize()}px"
        self.setFont(font)
        # Application QSS stops implicit font inheritance. Derive this local
        # rule from the current application font whenever that font changes.
        self.setStyleSheet(f"QWidget {{ font-size: {font_size}; }}")

    def _trace(self, event, **fields):
        owner = self._session
        identity = getattr(owner, "identity", None)
        round_state = getattr(owner, "round_state", None)
        join = getattr(owner, "join_event", None)
        pk_trace(event, **({"trace_id": getattr(owner, "trace_id", None),
                            "uid": getattr(identity, "uid", None),
                            "room_id": getattr(identity, "room_id", None),
                            "pk_id": getattr(round_state, "round_id", None),
                            "biz_session_id": getattr(round_state,
                                                      "biz_session_id", None),
                            "rtc_channel_id": getattr(join, "rtc_channel_id",
                                                      None),
                            "mode": self.mode.currentData(),
                            "session_enabled": self._session_enabled} | fields))

    def set_session_available(self, available, reason=""):
        self._session_enabled = available
        if not available:
            self._pending_start = None
            self._candidate_start = None
            if self.provider_readiness is not None:
                self.provider_readiness.cancel(self)
            self._close_settings()
        self._refresh_session_controls()
        if reason:
            self.status.setText(reason)

    def set_status(self, text):
        self.status.setText(text)

    def _open_settings(self):
        if self._shutdown or not self._session_enabled:
            return
        if self._settings_dialog is None:
            from startlive.PySide.window.pk_settings_dialog import \
                PkSettingsDialog
            from startlive.PySide.interface_adapters.pk.settings_controller import \
                PkSettingsController
            self._settings_dialog = PkSettingsDialog(self)
            self._settings_controller = PkSettingsController(
                self._workers, self._settings_dialog,
                identity_provider=self._identity_provider,
                confirmed=self._settings_confirmed)
            self._settings_dialog.changeRequested.connect(
                self._settings_controller.change)
            self._settings_dialog.refreshRequested.connect(
                self._settings_controller.refresh)
        self._settings_dialog.open()
        self._settings_dialog.raise_()
        self._settings_controller.refresh()

    def _open_encoder_settings(self):
        if self._shutdown or self.mode.currentData() == PkMode.TRADITIONAL:
            return
        if self._encoder_dialog is None:
            from startlive.PySide.widgets.pk_encoder_settings import \
                PkEncoderSettingsWidget
            self._encoder_dialog = PkEncoderSettingsWidget(
                self, manager=self._workers,
                is_active=lambda: self._connection_active)
            self._encoder_dialog.finished.connect(self._encoder_dialog_finished)
        self._encoder_dialog.show()
        self._encoder_dialog.raise_()
        self._encoder_dialog.activateWindow()

    def _encoder_dialog_finished(self, _):
        self._encoder_dialog = None

    def close_encoder_settings(self):
        if self._encoder_dialog is not None:
            self._encoder_dialog.close()
            self._encoder_dialog = None

    def _settings_confirmed(self, snapshot):
        controller = self._settings_controller
        if self._shutdown or not self._session_enabled or controller is None or controller.closed:
            return
        self._invitation_reception_by_mode.update({
            PkMode.VIDEO: snapshot.preferences.accept_pk,
            PkMode.VIDEO_LINK: snapshot.preferences.accept_connection})
        self.set_invitation_reception(snapshot.preferences.accept_connection
                                      if self.mode.currentData() == PkMode.VIDEO_LINK else snapshot.preferences.accept_pk)
        self._invitation_reception_identity = controller.identity

    def _close_settings(self):
        if self._settings_controller is not None:
            self._settings_controller.close()
            self._settings_controller = None
        if self._settings_dialog is not None:
            self._settings_dialog.close()
            self._settings_dialog.deleteLater()
            self._settings_dialog = None
        self._invitation_reception_identity = None
        self._invitation_reception = None
        self._invitation_reception_by_mode.clear()

    def _check_reception_account(self, identity):
        if self._invitation_reception_identity is not None and identity != self._invitation_reception_identity:
            self._invitation_reception = None
            self._invitation_reception_by_mode.clear()
            self._invitation_reception_identity = None

    def set_round_info(self, info: PkRoundDisplay | None):
        """Update persistent round details without changing media or controls."""
        if info is None:
            self.round_info.clear()
            self.round_info.hide()
            return
        stage = "本轮 PK 已结束" if info.ended else {
            NativePkState.IDLE: "等待 PK",
            NativePkState.STARTING: "正在发起 PK",
            NativePkState.MATCHING: "正在匹配",
            NativePkState.SELECTING_USER: "正在选择对手",
            NativePkState.PREPARING: "PK 准备中",
            NativePkState.PKING: "PK 进行中",
            NativePkState.PUNISHING: "惩罚阶段",
            NativePkState.END: "本轮 PK 已结束",
        }.get(info.state, "PK 状态已更新")
        # Buzzing (server301), Freezing and Exit have no promoted UI wording.
        heading = f"{stage} · 回合 {info.round_id}" if info.round_id else stage
        if info.remaining_seconds is not None:
            heading += f" · 剩余约 {info.remaining_seconds} 秒"
        own = f"我方 UID：{info.own_uid}"
        if info.own_name:
            own += f"（{info.own_name}）"
        peer = f"对方 UID：{info.peer_search}" if info.peer_search else "对方：等待确认"
        if info.peer_name:
            peer += f"（{info.peer_name}）"
        lines = [heading]
        for identity, votes, votes_text, result in (
                (own, info.own_votes, info.own_votes_text, info.own_result),
                (peer, info.peer_votes, info.peer_votes_text, info.peer_result),
        ):
            score = votes_text or (str(votes) if votes is not None else "—")
            text = f"{identity} · 分数：{score}"
            if result in (0, 1, 2):
                text += " · " + {0: "负", 1: "胜", 2: "平"}[result]
            lines.append(text)
        lines.extend(
            text for text in (info.status_message, info.punish_text) if text)
        self.round_info.setText("\n".join(lines))
        self.round_info.show()

    def set_continuous_status(self, enabled, editable):
        with QSignalBlocker(self.continuous):
            self.continuous.setChecked(enabled)
        self._continuous_editable = editable
        self._refresh_session_controls()

    def _output_readiness(self, mode):
        from startlive.core import app_state
        from startlive.core.pk.output_readiness import output_readiness
        return output_readiness(app_state.obs_output_status, mode)

    def _check_video_provider(self, mode, resume):
        if mode == PkMode.TRADITIONAL:
            return True
        self._ensure_video_ui()
        if self.provider_readiness.ready:
            return True
        if self.provider_readiness.waiting(self):
            return False
        identity = self._identity_provider()

        def finished():
            if self._shutdown or not self._session_enabled:
                return
            if self._identity_provider() != identity:
                raise PkError("账号或直播间已变更，请重新发起 PK 操作")
            self._refresh_session_controls()
            resume()

        def failed(error):
            if not self._shutdown:
                self.set_status(str(error))
                self._refresh_session_controls()

        self.set_status("正在检查视频 PK 组件…")
        self.provider_readiness.ensure(self, finished, failed)
        self._refresh_session_controls()
        return False

    def _start_session(self, options, *, invitation_only=False):
        self._trace("ui.session_start.requested", selected_mode=options.mode,
                    peer_search=options.peer_search,
                    continuous=options.continuous,
                    invitation_only=invitation_only)
        if self._shutdown or not self._session_enabled or self._pending_start is not None:
            return
        if self._controls_busy() or (
                self._session is not None and not self._session.closed
                and getattr(self._session, "invitation_only",
                            False) and not self._idle_listener()):
            self._trace("ui.session_start.ignored", reason="current_owner_busy")
            return
        try:
            if not self._check_video_provider(options.mode,
                                              lambda: self._start_session(
                                                  options,
                                                  invitation_only=invitation_only)):
                return
            identity = self._identity_provider()
            if invitation_only:
                self._check_reception_account(identity)
                if self._invitation_reception is False:
                    self.set_status(
                        "当前已关闭接受 PK 邀请，请在 PK / 连线设置中开启")
                    self._open_settings()
                    return
                # Listening is an explicit local action, not a settings write.
                if self._invitation_reception is None:
                    self.set_invitation_reception(True)
                if self._idle_listener():
                    return
            if self._session is not None:
                # Preserve one explicit action while both old push workers drain.
                # The owner reference and account snapshot also guard late callbacks.
                self._pending_start = (options, identity, invitation_only,
                                       self._session)
                self._session.close()
                self._session.tick()
                if self._session.manager.busy:
                    self._trace("ui.session_start.deferred",
                                reason="previous_owner_retiring")
                    self._refresh_session_controls()
                    self.set_status("正在切换 PK 会话，关闭监听后将自动继续…")
                    return
                self._pending_start = None
            self._create_session(options, identity,
                                 invitation_only=invitation_only)
        except Exception as error:
            self._pending_start = None
            self._trace("ui.session_start.failed",
                        error_type=type(error).__name__, error=str(error))
            self.set_status(str(error))
            self._refresh_session_controls()

    def _create_session(self, options, identity, *, invitation_only):
        self._check_reception_account(identity)
        owner = self._session_factory(self._workers, identity, options, self,
                                      readiness=self._output_readiness,
                                      provider_readiness=self.provider_readiness,
                                      invitation_only=invitation_only)
        self._session = owner
        self._continuous_editable = True
        self._trace("ui.session_created")
        try:
            if self._invitation_reception is not None:
                self._apply_reception(owner, self._invitation_reception)
            owner.start()
        except Exception:
            owner.close()
            raise

    def _drain_pending_start(self):
        pending = self._pending_start
        if pending is None:
            return
        options, identity, invitation_only, previous = pending
        if self._shutdown or not self._session_enabled or self._session is not previous:
            self._pending_start = None
            self._refresh_session_controls()
            return
        if previous.manager.busy:
            return
        try:
            if self._identity_provider() != identity:
                raise PkError("登录账号已改变，待启动的 PK 已取消，请重新选择")
            self._pending_start = None
            self._create_session(options, identity,
                                 invitation_only=invitation_only)
        except Exception as error:
            self._pending_start = None
            self._trace("ui.session_start.failed",
                        error_type=type(error).__name__, error=str(error))
            self.set_status(str(error))
        self._refresh_session_controls()

    def _idle_listener(self):
        return bool(getattr(self._session, "idle_invitation_listener", False))

    def _controls_busy(self):
        return ((
                        self._active and not self._idle_listener()) or self._connection_active
                or self._pending_start is not None or self._candidate_dialog is not None
                or self._invitation_dialog is not None
                or (
                        self.provider_readiness is not None and self.provider_readiness.waiting(
                    self)))

    @staticmethod
    def _apply_reception(owner, enabled):
        setter = getattr(owner, "set_invitation_reception", None)
        if setter is not None and not owner.closed:
            setter(enabled)

    def set_invitation_reception(self, enabled):
        """Apply a local reception preference without starting or ending a call."""
        if type(enabled) is not bool:
            raise PkError("邀请接收状态必须是开或关")
        self._invitation_reception = enabled
        self._invitation_reception_by_mode[self.mode.currentData()] = enabled
        self._trace("ui.invitation_reception.changed", enabled=enabled)
        if self._session is not None:
            self._apply_reception(self._session,
                                  enabled and self._candidate_dialog is None
                                  and self._pending_start is None)
        self._refresh_session_controls()

    def _session_action(self, method, *args):
        self._trace("ui.session_action", action=method)
        if self._session is not None:
            try:
                getattr(self._session, method)(*args)
            except Exception as error:
                self._trace("ui.session_action.failed", action=method,
                            error_type=type(error).__name__, error=str(error))
                self.set_status(str(error))

    def _change_continuous(self, enabled):
        self._trace("ui.continuous_selected", enabled=enabled)
        if (self._session is not None and not self._session.closed
                and not getattr(self._session, "invitation_only", False)):
            self._session_action("set_continuous", enabled)

    def _request_invitation_wait(self):
        self._trace("ui.invitation_wait.requested")
        if (
                self._session_factory is not None and self._session_enabled and not self._controls_busy()
                and self.mode.currentData() != PkMode.TRADITIONAL):
            self._start_session(PkOptions(self.mode.currentData()),
                                invitation_only=True)

    def set_invitation_waiting(self, waiting):
        self._invitation_waiting = waiting
        self._refresh_session_controls()

    def show_invitation(self, event):
        if self._invitation_dialog is not None:
            return
        owner = self._session
        peer_search = event.peer_search if event.peer_search is not None and event.peer_search > 0 else event.initiator
        label = "视频连线" if self.mode.currentData() == PkMode.VIDEO_LINK else "视频 PK"
        dialog = QMessageBox(QMessageBox.Icon.Question, label + "邀请",
                             f"是否接受 UID {peer_search} 的{label}邀请？",
                             QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                             self)
        self._invitation_dialog = dialog

        def answered(result):
            if self._invitation_dialog is not dialog:
                return
            self._invitation_dialog = None
            if owner is self._session and owner is not None and not owner.closed:
                self._session_action("answer_invitation", event,
                                     result == QMessageBox.StandardButton.Yes)
            dialog.deleteLater()

        dialog.finished.connect(answered)
        dialog.open()

    def set_invitation_remaining(self, seconds):
        if self._invitation_dialog is not None:
            self._invitation_dialog.setInformativeText(
                f"请在 {seconds} 秒内选择")

    def dismiss_invitation(self):
        dialog, self._invitation_dialog = self._invitation_dialog, None
        if dialog is not None:
            dialog.blockSignals(True)
            dialog.reject()
            dialog.deleteLater()

    def set_active(self, active):
        self._active = active
        self._refresh_session_controls()

    def set_connection_active(self, active):
        """Round completion must not clear a still-live interaction/RTC link."""
        if self._connection_active and not active and self.remote_buffer is not None:
            self.remote_buffer.clear()
            self.remote_view.reset()
        self._connection_active = active
        self._refresh_session_controls()

    def set_publisher_available(self, *, audio, video):
        from startlive.core.pk.states.mute import RtcMuteState
        self._publisher_available = {"audio": audio, "video": video}
        for media, available in self._publisher_available.items():
            if not available:
                self.set_publisher_mute_state(media, RtcMuteState())
        self._refresh_publisher_controls()

    def set_publisher_mute_state(self, media, state):
        self._publisher_mute_states[media] = state
        with QSignalBlocker(self._publisher_controls[media]):
            self._publisher_controls[media].setChecked(state.local_muted)
        self._refresh_publisher_controls()

    def _request_publisher_mute(self, media, muted):
        self._trace("ui.publisher_mute.requested", media=media, muted=muted)
        state = self._publisher_mute_states[media]
        # Show the applied local state until the owning worker reports a change.
        self.set_publisher_mute_state(media, state)
        if (self._session_enabled and self._connection_active and
                self._publisher_available[media] and not state.pending):
            self._session_action("set_publisher_muted", media, muted)

    def _refresh_publisher_controls(self):
        for media, control in self._publisher_controls.items():
            control.setEnabled(
                self._session_enabled and self._connection_active and
                self._publisher_available[media] and not
                self._publisher_mute_states[media].pending)
        if hasattr(self, "remote_video_mute"):
            remote_ready = self._connection_active
            if self.mode.currentData() != PkMode.VIDEO:
                rtc = getattr(self._session, "rtc", None)
                remote_ready = remote_ready and bool(
                    getattr(getattr(rtc, "business_mute", None), "initialized",
                            False))
            self.remote_video_mute.setVisible(
                self.mode.currentData() == PkMode.VIDEO_LINK)
            self.remote_video_mute.setEnabled(remote_ready)
            self.remote_mute.setEnabled(remote_ready)

    def _refresh_session_controls(self):
        self.settings_button.setEnabled(
            self._session_enabled and not self._shutdown)
        busy = self._controls_busy()
        self.mode.setEnabled(not busy)
        self._refresh_match_options()
        self.start_button.setEnabled(self._session_enabled and not busy)
        self.wait_invitation_button.setEnabled(
            self._session_enabled and not busy
            and self.mode.currentData() != PkMode.TRADITIONAL)
        self.stop_button.setEnabled(
            self._session_enabled and (self._active or self._idle_listener()))
        self.disconnect_button.setEnabled(
            self._session_enabled and self._connection_active)
        self.convert_pk_button.setEnabled(
            self._session_enabled and self._connection_active
            and self._session is not None and self._session.round_state.state == NativePkState.IDLE
            and getattr(self._session.rtc, "publisher_ready", False)
            and not getattr(self._session.flow, "starting_pk", False))
        if self._session is None or self._session.closed or self._idle_listener():
            self.continuous.setEnabled(self._session_enabled and not busy)
        else:
            self.continuous.setEnabled(
                self._session_enabled and self._continuous_editable
                and not getattr(self._session, "invitation_only", False)
                and self._pending_start is None and self._candidate_dialog is None)

    def _refresh_match_options(self):
        video = self.mode.currentData() == PkMode.VIDEO
        link = self.mode.currentData() == PkMode.VIDEO_LINK
        self.random_match.setVisible(video)
        self.peer_search.setVisible(video)
        self.encoder_settings_button.setVisible(video or link)
        self.convert_pk_button.setVisible(link)
        self.continuous.setVisible(not link)
        self.start_button.setText("邀请连线" if link else "开始 PK")
        self.continuous.setText("连续随机 PK" if video else "连续 PK")
        if not video:
            with QSignalBlocker(self.random_match):
                self.random_match.setChecked(True)
        busy = self._controls_busy()
        self.random_match.setEnabled(video and not busy)
        self.peer_search.setEnabled(
            video and not busy and not self.random_match.isChecked())
        self.disconnect_button.setVisible(
            video or link or self._connection_active)
        self.wait_invitation_button.setVisible(video or link)
        self.wait_invitation_button.setEnabled(
            self._session_enabled and (video or link) and not busy)
        self.stop_button.setText(
            "停止监听" if self._idle_listener() else "结束本轮" if video else "结束 PK")
        self._refresh_publisher_controls()

    def _request_start(self):
        self._trace("ui.start.requested", random=self.random_match.isChecked(),
                    continuous=self.continuous.isChecked())
        if self._shutdown or not self._session_enabled or self._controls_busy():
            return
        uid = None
        if not self.random_match.isChecked():
            value = self.peer_search.text().strip()
            if not value.isascii() or not value.isdecimal() or not 0 < int(
                    value) < 1 << 64:
                self._trace("ui.start.ignored", reason="invalid_peer_uid")
                self.status.setText("请输入有效的主播 UID 或房间号")
                return
            uid = int(value)
        options = PkOptions(PkMode(self.mode.currentData()), uid,
                            self.continuous.isChecked() if self.mode.currentData() != PkMode.VIDEO_LINK else False)
        if (
                options.mode is PkMode.VIDEO and uid is not None) or options.mode is PkMode.VIDEO_LINK:
            if self._candidate_dialog is not None:
                self._candidate_dialog.raise_()
                return
            try:
                if not self._check_video_provider(options.mode,
                                                  self._request_start):
                    return
                identity = self._identity_provider()
            except Exception as error:
                self._trace("ui.candidate_search.failed",
                            error_type=type(error).__name__, error=str(error))
                self.status.setText(str(error))
                return
            from startlive.PySide.window.pk_search_dialog import PkSearchDialog
            dialog = PkSearchDialog(self._workers, identity,
                                    self.peer_search.text().strip(), self,
                                    video_link=options.mode == PkMode.VIDEO_LINK)
            self._trace("ui.candidate_search.opened", uid=identity.uid,
                        room_id=identity.room_id,
                        requested_search=self.peer_search.text().strip())
            self._candidate_dialog = dialog
            self._candidate_start = None
            if self._idle_listener():
                self._search_listener = (self._session, getattr(self._session,
                                                                "invitation_display_allowed",
                                                                True))
                self._apply_reception(self._session, False)
            self._refresh_session_controls()
            dialog.candidateSelected.connect(
                lambda candidate: self._candidate_selected(
                    dialog,
                    PkOptions(options.mode, candidate.uid, options.continuous,
                              candidate), identity))
            dialog.finished.connect(lambda _: self._candidate_closed(dialog))
            dialog.show()
            dialog.search()
            return
        self.startRequested.emit(options)

    def _candidate_selected(self, dialog, options, identity):
        if self._candidate_dialog is dialog and not self._shutdown and self._session_enabled:
            self._candidate_start = (options, identity)

    def _candidate_closed(self, dialog):
        if self._candidate_dialog is not dialog:
            return
        selected, self._candidate_start = self._candidate_start, None
        self._candidate_dialog = None
        dialog.deleteLater()
        try:
            if selected is not None and not self._shutdown and self._session_enabled:
                options, identity = selected
                if self._identity_provider() != identity:
                    raise PkError("登录账号已改变，请重新查找 PK 对手")
                self.startRequested.emit(options)
        except Exception as error:
            self.set_status(str(error))
        listener, self._search_listener = self._search_listener, None
        if listener is not None and not self._shutdown and self._session_enabled:
            owner, previous = listener
            if self._session is owner and not owner.closed:
                self._apply_reception(owner,
                                      previous if self._invitation_reception is None else self._invitation_reception)
        self._refresh_session_controls()

    def _set_video_crop(self, crop):
        self.publish_buffer.video_crop = crop
        self.local_view.set_crop(crop)

    def _update_video_mode(self):
        self._invitation_reception = self._invitation_reception_by_mode.get(
            self.mode.currentData())
        video = self.mode.currentData() != PkMode.TRADITIONAL
        if video:
            self._ensure_video_ui()
        if self.local_view is not None:
            for widget in (self.local_view, self.remote_view, self._video_hint):
                widget.setVisible(video)
            if video:
                self.local_view.video.show()
                self.remote_view.video.show()
                self.crop_button.show()
                self.publisher_video_mute.setVisible(
                    self.mode.currentData() == PkMode.VIDEO)
                self._prepare_video_preview()
            else:
                self.provider_readiness.cancel(self._preview_owner)
                self._stop_preview()
                self.close_encoder_settings()
        if not video:
            self.set_status("选择经典 PK 开始。")
        self._fit_to_screen()
        if self.isVisible():
            self._center_on_screen()

    def _stop_preview(self):
        if self.local_view is None:
            return
        self._preview_retry.stop()
        self._media_timer.stop()
        self.audio_timer.stop()
        if self._preview_worker is not None:
            self._preview_worker.stop()
        self.crop_selector.hide()
        self.local_view.reset()
        self.remote_view.reset()
        for buffer in (self.local_buffer, self.remote_buffer,
                       self.publish_buffer):
            buffer.clear()

    def _prepare_video_preview(self):
        if self._shutdown or self.mode.currentData() == PkMode.TRADITIONAL:
            return
        self.set_status("正在检查视频 PK 组件…")
        self.provider_readiness.ensure(
            self._preview_owner, self._start_preview,
            self._preview_dependency_failed)

    def _preview_dependency_failed(self, error):
        if not self._shutdown and self.mode.currentData() != PkMode.TRADITIONAL:
            self.set_status(str(error))

    def _fit_to_screen(self):
        """Fit equal 5:4 previews to logical screen pixels, preserving source frames."""
        self.ensurePolished()
        if self.mode.currentData() == PkMode.TRADITIONAL:
            layout = self.layout()
            for index in range(layout.count()):
                child = layout.itemAt(index).layout()
                if child is not None:
                    child.invalidate()
            layout.invalidate()
            self.setFixedSize(layout.sizeHint())
            return
        for view in (self.local_view, self.remote_view):
            view.video.setFixedSize(600, 480)
            view.layout().invalidate()
            view.layout().activate()
            view.updateGeometry()
        layout = self.layout()
        for index in range(layout.count()):
            child = layout.itemAt(index).layout()
            if child is not None:
                child.invalidate()
        layout.invalidate()
        preferred = layout.sizeHint()
        available = self.screen().availableGeometry()
        # Leave room for window borders/title bar and a desktop margin. Qt's
        # availableGeometry already accounts for the taskbar and display scaling.
        extra_width = preferred.width() - 1200
        extra_height = preferred.height() - 480
        units = max(1, min(120, (available.width() - 32 - extra_width) // 10,
                           (available.height() - 64 - extra_height) // 4))
        for view in (self.local_view, self.remote_view):
            view.video.setFixedSize(units * 5, units * 4)
            view.layout().invalidate()
            view.layout().activate()
            view.updateGeometry()
        for index in range(layout.count()):
            child = layout.itemAt(index).layout()
            if child is not None:
                child.invalidate()
        layout.invalidate()
        self.setFixedSize(layout.sizeHint())

    def showEvent(self, event):
        self._fit_to_screen()
        super().showEvent(event)
        if not event.spontaneous():
            self._center_on_screen()
        if self.mode.currentData() != PkMode.TRADITIONAL:
            self._prepare_video_preview()

    def _center_on_screen(self):
        frame = self.frameGeometry()
        frame.moveCenter(self.screen().availableGeometry().center())
        self.move(frame.topLeft())

    def _start_preview(self):
        if (self._shutdown or not self.isVisible()
                or self.mode.currentData() == PkMode.TRADITIONAL
                or not self.provider_readiness.ready
                or self._preview_worker is not None):
            return
        from startlive.core.workers.pk.obs_media import ObsMediaWorker

        self._preview_retry.stop()
        self._media_timer.start()
        self.audio_timer.start()
        self._trace("ui.preview.requested", enabled=True)
        presenter = PkPresenter(
            finished=lambda: self._preview_stopped(worker),
            failed=lambda error: self._preview_failed(error, worker),
            progress=lambda _: self._preview_connected(worker))
        worker = self._preview_worker = ObsMediaWorker(
            presenter, (self.local_buffer, self.publish_buffer))
        try:
            self._preview_future = self._workers.submit(self._preview_worker,
                                                        on_progress=True)
        except Exception as error:
            self._preview_failed(error, worker)
            return
        self.status.setText("正在等待 OBS 采集插件…")

    def _preview_connected(self, worker):
        if (worker is self._preview_worker and worker.is_running
                and not self._shutdown and self.mode.currentData() != PkMode.TRADITIONAL):
            self.status.setText("OBS 已连接")

    def _preview_stopped(self, worker):
        if worker is not self._preview_worker:
            return
        self._preview_worker = self._preview_future = None
        self.local_view.reset()
        self.local_buffer.clear()
        self.publish_buffer.clear()
        if self._classic_audio:
            self._start_classic_capture()
        elif not self._shutdown and self.mode.currentData() != PkMode.TRADITIONAL:
            self._preview_retry.start()

    def _preview_failed(self, error, worker):
        if worker is not self._preview_worker:
            return
        self._preview_stopped(worker)
        if not self._shutdown and self.mode.currentData() != PkMode.TRADITIONAL:
            self.status.setText(f"{error}；将自动重试连接 OBS。")

    def _refresh_state(self):
        self.output_status.setText("直播输出：" + self._output_readiness(
            self.mode.currentData()).reason)
        if self._session is not None:
            self._session.tick()
        self._refresh_session_controls()
        self._drain_pending_start()
        # Cancellation does not trigger prepare_success_view in WorkerManager.
        if self._preview_future and self._preview_future.done() and self._preview_worker and not self._preview_worker.is_running:
            self._preview_stopped(self._preview_worker)

    def _refresh_media(self):
        for buffer, view in ((self.local_buffer, self.local_view),
                             (self.remote_buffer, self.remote_view)):
            packet = buffer.take(1)
            if packet and not (
                    view is self.remote_view and self.remote_video_mute.isChecked()):
                view.show_packet(packet)

    def _refresh_audio(self):
        # Audio delivery must not wait for the 33 ms video/business refresh.
        for buffer, view in ((self.local_buffer, self.local_view),
                             (self.remote_buffer, self.remote_view)):
            for _ in range(16):
                packet = buffer.take(2)
                if packet is None:
                    break
                view.show_packet(packet)

    def closeEvent(self, event):
        self._trace("ui.close.requested", active=self._active,
                    connection_active=self._connection_active)
        if not self._shutdown and (self._active or self._connection_active):
            self.status.setText(
                "请先断开视频连线，再关闭窗口" if self._connection_active
                else "请先结束 PK，再关闭窗口")
            event.ignore()
            return
        self.shutdown()
        super().closeEvent(event)

    def reject(self):
        self._trace("ui.dismiss.requested", active=self._active,
                    connection_active=self._connection_active)
        if not self._shutdown and (self._active or self._connection_active):
            self.status.setText(
                "请先断开视频连线，再关闭窗口" if self._connection_active
                else "请先结束 PK，再关闭窗口")
            return
        self.shutdown()
        super().reject()

    def shutdown(self):
        if self._shutdown:
            return
        self._trace("ui.shutdown")
        self._shutdown = True
        self._stop_preview()
        self._close_settings()
        self.close_encoder_settings()
        self._pending_start = self._candidate_start = None
        if self._session is not None:
            self._session.close()
        self.dismiss_invitation()
        if self._candidate_dialog is not None:
            self._candidate_dialog.reject()
        self.timer.stop()
        if self.provider_readiness is not None:
            self.provider_readiness.close()
        self._dispatcher.close()
        self._workers.shutdown(wait=False)
