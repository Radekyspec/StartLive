"""PK video preferences with asynchronous hardware discovery and autosave."""
from functools import partial
from weakref import ref

from PySide6.QtCore import Qt, QTimer, QSignalBlocker, Slot
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from startlive.PySide.states.pk_encoder import PKEncoderEvents
from startlive.core import app_state
from startlive.core.constant.pk_encoder import SCALE_MODES
from startlive.core.constant.pk_video_config import DEFAULT_VIDEO_CONFIG
from startlive.core.constant.settings import SettingsName
from startlive.core.pk.states.encoder import VideoEncodingConfig, aq_policy, \
    preset_choices, translate_preset
from startlive.core.workers.base.CallbackPresenter import CallbackPresenter
from startlive.core.workers.pk.scan_encoders import ScanPkEncodersWorker


def _emit_state_changed(bridge_ref):
    bridge = bridge_ref()
    if bridge is not None:
        try:
            bridge.state_changed.emit("runtime")
        except RuntimeError:
            pass  # The dialog was destroyed after a queued worker notification.


class PkEncoderSettingsWidget(QDialog):
    """Four editable preferences; active RTC sessions retain their snapshot."""

    def __init__(self, parent=None, *, manager, is_active=lambda: False):
        super().__init__(parent)
        self.setWindowTitle("PK 视频编码设置")
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.resize(560, 450)
        self._is_active = is_active
        self._manager = manager
        self._closed = False
        self._probe_worker = self._detection = None
        self._detect_generation = 0
        self._cancel_requested = False
        self._known_encoders = ()
        self._probe_timeouts = []
        self._loading = True
        self._pending_save = False
        self._events = PKEncoderEvents(self)
        self._events.state_changed.connect(
            self._on_state_changed, Qt.ConnectionType.QueuedConnection)
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(450)
        self._save_timer.timeout.connect(self._persist)
        self._build_ui()
        self._load()
        self._connect_changes()
        self._loading = False
        self._runtime_state_listener = partial(_emit_state_changed,
                                               ref(self._events))
        app_state.pk_encoder_runtime.subscribe(self._runtime_state_listener)
        self._render_runtime()
        self._detect()

    def _build_ui(self):
        page = QVBoxLayout(self)
        hint = QLabel("设置用于发送给 PK 对方的画面，下次视频连接时生效。")
        hint.setWordWrap(True)
        page.addWidget(hint)
        form = QFormLayout()
        self.encoder = QComboBox()
        self.encoder.addItem("自动选择 H.264 编码器", "auto")
        self.encoder.addItem("x264 (CPU)", "libx264")
        form.addRow("视频编码器", self.encoder)
        self.codec_refresh = QPushButton("重新检测可用编码器")
        self.codec_refresh.clicked.connect(self._detect)
        form.addRow(self.codec_refresh)
        self.codec_notice = QLabel()
        self.codec_notice.setWordWrap(True)
        form.addRow(self.codec_notice)

        self.preset = QComboBox()
        self.preset_caption = QLabel("编码预设")
        form.addRow(self.preset_caption, self.preset)
        self.spatial_aq = QCheckBox("开启 AQ")
        self.spatial_aq.setToolTip(
            "适用于 x264、NVIDIA NVENC 和 AMD AV1；SVT-AV1 的 CBR 模式固定开启。")
        form.addRow("自适应量化", self.spatial_aq)
        self.scale_mode = QComboBox()
        for value, label in SCALE_MODES:
            self.scale_mode.addItem(label, value)
        form.addRow("缩放滤镜", self.scale_mode)
        page.addLayout(form)
        config = DEFAULT_VIDEO_CONFIG
        self.fixed = QLabel(
            f"固定输出目标：{config.width}×{config.height} · {config.frame_rate} FPS\n"
            f"{config.rate_control} · 目标码率 {config.bitrate_kbps} Kbps · "
            f"B 帧 {config.max_b_frames} · 关键帧间隔 {config.keyframe_interval} 秒\n"
            "目标码率仅受编码协商上限约束，带宽反馈只记录日志。")
        self.fixed.setWordWrap(True)
        page.addWidget(self.fixed)
        self.runtime = QLabel()
        self.runtime.setWordWrap(True)
        self.runtime.setToolTip(
            "按最近约 1 秒实际发送的视频 RTP 数据量计算，包含 RTP 包头，"
            "不含音频、重传及网络封装开销；不代表对端实际接收码率。")
        page.addWidget(self.runtime)
        self.message = QLabel()
        self.message.setWordWrap(True)
        page.addWidget(self.message)
        page.addStretch()
        actions = QHBoxLayout()
        actions.addStretch()
        close_button = QPushButton("关闭")
        close_button.clicked.connect(self.close)
        actions.addWidget(close_button)
        page.addLayout(actions)

    def _load(self):
        config = app_state.pk_encoder_settings["config"]
        index = self.encoder.findData(config.encoder)
        if index == -1:
            self.encoder.addItem(config.encoder + "（未检测）", config.encoder)
            index = self.encoder.findData(config.encoder)
        self.encoder.setCurrentIndex(index)
        self._set_preset_choices(config.encoder, config.preset)
        self.spatial_aq.setChecked(config.spatial_aq)
        self.scale_mode.setCurrentIndex(
            self.scale_mode.findData(config.scale_mode))
        self._encoder_changed()

    def _connect_changes(self):
        for widget in (self.encoder, self.preset, self.scale_mode):
            widget.currentIndexChanged.connect(self._on_settings_changed)
        self.spatial_aq.toggled.connect(self._on_settings_changed)

    def _set_preset_choices(self, name, value):
        choices = preset_choices(name)
        selected = translate_preset(name, value or "quality")
        labels = {"performance": "速度优先", "balanced": "均衡",
                  "quality": "高质量",
                  "p1": "P1（速度优先）", "p4": "P4（均衡）", "p7": "P7（高质量）"}
        with QSignalBlocker(self.preset):
            if tuple(self.preset.itemData(i) for i in
                     range(self.preset.count())) != choices:
                self.preset.clear()
                for option in choices:
                    self.preset.addItem(labels.get(option, option), option)
            self.preset.setCurrentIndex(self.preset.findData(selected))
        self.preset_caption.setText(
            "x264 预设" if name in ("libx264", "auto") else
            "NVENC 预设" if name in ("h264_nvenc", "av1_nvenc") else "编码预设")
        self.preset.setToolTip(
            "SVT-AV1：高质量 8，均衡 10，速度优先 12。软件编码占用 CPU，"
            "实际帧率取决于处理器性能和画面复杂度。" if name == "libsvtav1" else "")

    def _encoder_changed(self, *_):
        name = self.encoder.currentData()
        self._set_preset_choices(name, self.preset.currentData())
        policy = aq_policy(name)
        self.spatial_aq.setEnabled(policy == "optional")
        self.spatial_aq.setText({"required": "固定开启 AQ（CBR 要求）",
                                 "optional": "开启 AQ",
                                 "unavailable": "当前编码器未提供 AQ 开关"}[
                                    policy])
        if policy != "optional":
            with QSignalBlocker(self.spatial_aq):
                self.spatial_aq.setChecked(policy == "required")

    def _read_config(self):
        return VideoEncodingConfig(
            encoder=self.encoder.currentData(),
            preset=self.preset.currentData(),
            spatial_aq=self.spatial_aq.isChecked(),
            scale_mode=self.scale_mode.currentData())

    def _detect(self):
        if self._detection is not None:
            # The subprocess scanner observes cancellation and terminates its
            # active child, without waiting for the driver on the GUI thread.
            self._cancel_requested = True
            self._probe_worker.cancel_scan()
            self.codec_refresh.setEnabled(False)
            self.codec_notice.setText("正在取消编码器检测…")
            return
        self._detect_generation += 1
        generation = self._detect_generation
        self._cancel_requested = False
        self._probe_timeouts = []
        presenter = CallbackPresenter(
            finished=partial(self._on_probe_finished, generation),
            failed=partial(self._on_probe_failed, generation),
            progress=partial(self._on_probe_progress, generation))
        self._probe_worker = ScanPkEncodersWorker(presenter)
        try:
            self._detection = self._manager.submit(self._probe_worker,
                                                   on_progress=True)
        except Exception as error:
            self._on_probe_failed(generation, error)
            return
        self.codec_refresh.setEnabled(True)
        self.codec_refresh.setText("取消检测")
        self.codec_notice.setText(
            "正在检测编码器…")

    @Slot(int, int, int, object, str)
    def _on_probe_progress(self, generation, index, count, choice, status):
        if (
                self._closed or generation != self._detect_generation or self._detection is None
                or self._cancel_requested):
            return
        if status == "running":
            self.codec_notice.setText(
                f"正在检测 {index}/{count}：{choice.label}")
        elif status == "timeout":
            self._probe_timeouts.append(choice.label)
            self.codec_notice.setText(
                f"{choice.label} 检测超时，正在检测下一个编码器…")

    @Slot(int, object)
    def _on_probe_finished(self, generation, detected):
        if self._closed or generation != self._detect_generation:
            return
        self._detection = None
        self.codec_refresh.setEnabled(True)
        self.codec_refresh.setText("重新检测可用编码器")
        if detected is None:
            self.codec_notice.setText("检测已取消，保留之前的编码器列表。")
            return
        self._known_encoders = detected
        previous = self.encoder.currentData()
        with QSignalBlocker(self.encoder):
            self.encoder.clear()
            self.encoder.addItem("自动选择 H.264 编码器", "auto")
            for item in self._known_encoders:
                self.encoder.addItem(item.label, item.name)
            if self.encoder.findData("libx264") < 0:
                self.encoder.addItem("x264 (CPU，尚未通过检测)", "libx264")
            if previous and self.encoder.findData(previous) == -1:
                self.encoder.addItem(f"{previous}（当前不可用）",
                                     previous)
            self.encoder.setCurrentIndex(
                max(0, self.encoder.findData(previous)))
        summary = ("已通过试编码：" + "、".join(
            item.label for item in self._known_encoders)
                   if self._known_encoders else
                   "没有通过试编码的视频编码器，请检查 PyAV/FFmpeg 安装")
        if self._probe_timeouts:
            summary += "\n检测超时：" + "、".join(
                self._probe_timeouts)
        self.codec_notice.setText(summary)
        self._encoder_changed()

    def _on_probe_failed(self, generation, error):
        if self._closed or generation != self._detect_generation:
            return
        self._detection = None
        self.codec_refresh.setEnabled(True)
        self.codec_refresh.setText("重新检测可用编码器")
        self.codec_notice.setText(f"检测失败：{type(error).__name__}")

    @Slot(str)
    def _on_state_changed(self, _source):
        self._render_runtime()

    def _render_runtime(self):
        state = app_state.pk_encoder_runtime.as_dict()
        bitrate = state["sent_bitrate_bps"]
        measured = f"{bitrate / 1000:.0f} Kbps" if bitrate is not None else "采样中…"
        self.runtime.setText(
            "本次 PK 编码器：" + state["backend"] +
            f" · 实际视频发送码率：{measured}" +
            (" · " + state["fallback_reason"] if state[
                "fallback_reason"] else "")
            if state["backend"] else "当前尚未开始 PK 视频编码")

    @Slot()
    def _on_settings_changed(self, *_):
        if self._loading:
            return
        self._encoder_changed()
        try:
            config = self._read_config()
        except (ValueError, TypeError) as error:
            self.message.setText("设置无效：" + str(error))
            return
        if app_state.pk_encoder_settings["config"] != config:
            app_state.pk_encoder_settings.update(config=config)
            self._pending_save = True
            self._save_timer.start()
            self.message.setText("设置已更新，正在自动保存…" +
                                 (
                                     " 下次视频连接生效。" if self._is_active() else ""))

    @Slot()
    def _persist(self):
        if not self._pending_save:
            return
        try:
            app_state.save_settings(SettingsName.PK_ENCODER)
        except Exception as error:
            self.message.setText("自动保存失败：" + str(error))
        else:
            self._pending_save = False
            self.message.setText("已自动保存，下次 PK 视频连接时使用新设置。")

    def _cleanup(self):
        if self._closed:
            return
        self._closed = True
        self._save_timer.stop()
        self._persist()
        app_state.pk_encoder_runtime.unsubscribe(self._runtime_state_listener)
        if self._detection is not None:
            self._manager.cancel(self._detection)

    def done(self, result):
        self._cleanup()
        super().done(result)

    def closeEvent(self, event):
        self._cleanup()
        super().closeEvent(event)
