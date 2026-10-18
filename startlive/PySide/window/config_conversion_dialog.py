from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout, QFrame,
    QHBoxLayout, QLabel,
    QLineEdit, QMessageBox, QPlainTextEdit, QPushButton, QSpinBox, QVBoxLayout,
)

from startlive.core.config_conversion.livehime import (
    ConversionError,
    convert_collection,
    default_data_root,
    discover_configs,
    export_collection,
    read_config,
)
from startlive.core.constant.config_conversion import FILTERED_SCENE_PREFIXES


class ConfigConversionDialog(QDialog):
    """Preview a local conversion and export the exact reviewed snapshot."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("配置转换 · 直播姬 → OBS")
        self.resize(780, 600)
        self.result = None
        layout = QVBoxLayout(self)
        description = QLabel(
            "将直播姬场景转换为 OBS 场景集合。无法识别的专用源、滤镜和转场会跳过。\n\n"
            "建议先退出直播姬，确保最新配置已保存。导出为新文件，素材仍使用原路径。"
        )
        description.setWordWrap(True)
        layout.addWidget(description)

        form = QFormLayout()
        discovery = QHBoxLayout()
        self.configs = QComboBox()
        self.configs.setMinimumContentsLength(16)
        self.configs.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.configs.setPlaceholderText("请选择已发现的场景配置")
        self.configs.setAccessibleName("已发现配置")
        self.configs.setToolTip(
            "列出自动查找或所选目录中的场景配置；选中后填入下方配置路径。")
        discovery.addWidget(self.configs, 1)
        self.detect_button = QPushButton("自动查找")
        self.detect_button.clicked.connect(self._discover)
        discovery.addWidget(self.detect_button)
        folder_button = QPushButton("选择配置目录…")
        folder_button.clicked.connect(self._browse_directory)
        discovery.addWidget(folder_button)
        discovery_label = QLabel("已发现配置")
        discovery_label.setBuddy(self.configs)
        form.addRow(discovery_label, discovery)

        source_row = QHBoxLayout()
        self.source_path = QLineEdit()
        self.source_path.setPlaceholderText(
            "选择 untitledv2.json 或 Scene Collection 中的 JSON")
        source_row.addWidget(self.source_path, 1)
        browse_button = QPushButton("选择文件…")
        browse_button.clicked.connect(self._browse_file)
        source_row.addWidget(browse_button)
        form.addRow("直播姬配置", source_row)
        self.collection_name = QLineEdit("直播姬转换")
        form.addRow("OBS 场景集合名称", self.collection_name)

        size_row = QHBoxLayout()
        size_row.setSpacing(8)
        self.canvas_width = QSpinBox()
        self.canvas_height = QSpinBox()
        for label, spin in (("宽", self.canvas_width),
                            ("高", self.canvas_height)):
            spin.setRange(0, 16384)
            spin.setSpecialValueText("自动检测")
            spin.setMinimumWidth(120)
            spin.setMaximumWidth(160)
            spin.setAccessibleName(f"原画布{label}度（像素）")
            dimension_label = QLabel(label)
            dimension_label.setBuddy(spin)
            size_row.addWidget(dimension_label)
            size_row.addWidget(spin)
            spin.valueChanged.connect(self._invalidate)
        separator = QLabel("×")
        separator.setAlignment(Qt.AlignmentFlag.AlignCenter)
        separator.setFixedWidth(32)
        separator_font = separator.font()
        separator_font.setBold(True)
        if separator_font.pointSizeF() > 0:
            separator_font.setPointSizeF(separator_font.pointSizeF() * 1.4)
        elif separator_font.pixelSize() > 0:
            separator_font.setPixelSize(round(separator_font.pixelSize() * 1.4))
        separator.setFont(separator_font)
        size_row.insertWidget(2, separator)
        size_row.addWidget(QLabel("px"))
        size_row.addStretch()
        form.addRow("原画布尺寸", size_row)
        layout.addLayout(form)
        hint = QLabel(
            "自动检测依据场景坐标。若无法检测，请填写直播姬原画布尺寸；横竖屏及双屏模式需在 OBS 中另行设置。")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        layout.addWidget(self._build_scene_filter())

        self.report = QPlainTextEdit()
        self.report.setReadOnly(True)
        layout.addWidget(self.report, 1)
        self.status = QLabel()
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        buttons = QHBoxLayout()
        self.analyze_button = QPushButton("分析并预览")
        self.analyze_button.clicked.connect(self._analyze)
        self.export_button = QPushButton("导出 OBS 配置…")
        self.export_button.setEnabled(False)
        self.export_button.clicked.connect(self._export)
        close_button = QPushButton("关闭")
        close_button.clicked.connect(self.close)
        buttons.addWidget(self.analyze_button)
        buttons.addStretch()
        buttons.addWidget(self.export_button)
        buttons.addWidget(close_button)
        layout.addLayout(buttons)
        self.source_path.textChanged.connect(self._invalidate)
        self.collection_name.textChanged.connect(self._invalidate)
        self.filter_prefixed_scenes.toggled.connect(self._invalidate)
        # activated also fires when the user reselects the current file.
        self.configs.activated.connect(self._select_config)
        self._discover()

    def _build_scene_filter(self):
        self.filter_card = QFrame()
        self.filter_card.setObjectName("sceneFilterCard")
        self.filter_card.setFrameShape(QFrame.Shape.StyledPanel)
        content = QVBoxLayout(self.filter_card)
        content.setContentsMargins(16, 12, 16, 12)
        content.setSpacing(8)
        header = QHBoxLayout()
        self.filter_prefixed_scenes = QCheckBox("按名称过滤场景")
        self.filter_prefixed_scenes.setObjectName("sceneFilterToggle")
        title_font = self.filter_prefixed_scenes.font()
        title_font.setBold(True)
        self.filter_prefixed_scenes.setFont(title_font)
        self.filter_prefixed_scenes.setMinimumHeight(28)
        self.filter_prefixed_scenes.setCursor(Qt.CursorShape.PointingHandCursor)
        self.filter_prefixed_scenes.setAccessibleDescription(
            "过滤以 Vertical、wDouble、xDouble 开头的场景，区分大小写"
        )
        header.addWidget(self.filter_prefixed_scenes)
        header.addStretch()
        content.addLayout(header)
        description = QLabel("跳过名称以以下前缀开头的场景：")
        description.setWordWrap(True)
        content.addWidget(description)
        prefixes = QHBoxLayout()
        prefixes.setSpacing(6)
        for prefix in FILTERED_SCENE_PREFIXES:
            chip = QLabel(prefix)
            chip.setProperty("role", "prefix")
            chip.setFrameShape(QFrame.Shape.StyledPanel)
            chip.setMargin(5)
            prefixes.addWidget(chip)
        prefixes.addStretch()
        content.addLayout(prefixes)
        note = QLabel("只使用横屏场景时推荐打开。更改后需重新分析预览")
        note.setWordWrap(True)
        content.addWidget(note)
        return self.filter_card

    def _invalidate(self, *_):
        self.result = None
        self.export_button.setEnabled(False)
        self.report.clear()
        self.status.setText("请点击「分析并预览」，检查转换结果后导出")

    def _discover(self, *_args, root=None):
        self._invalidate()
        try:
            paths = discover_configs(root)
        except OSError as exc:
            self.status.setText(f"无法查找配置：{exc}")
            return
        self.configs.blockSignals(True)
        self.configs.clear()
        for path in paths:
            self.configs.addItem(str(path), str(path))
        self.configs.blockSignals(False)
        if paths:
            self._select_config(0)
            self.status.setText(
                f"找到 {len(paths)} 个配置，优先列出支持分组的配置；请选择要转换的文件。")
        else:
            self.status.setText(
                "未找到配置。可手动选择 JSON，或选择 bililive/User Data、账号、Scene Collection 目录。")

    def _select_config(self, index):
        path = self.configs.itemData(index)
        if path:
            self._set_source(path)

    def _set_source(self, path):
        # Choosing the same path can mean Livehime has just saved new contents.
        self._invalidate()
        self.source_path.setText(path)
        self.canvas_width.setValue(0)
        self.canvas_height.setValue(0)

    def _browse_directory(self):
        path = QFileDialog.getExistingDirectory(
            self, "选择直播姬配置目录", str(default_data_root() or Path.home()))
        if path:
            self._discover(root=Path(path))

    def _browse_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择直播姬场景配置",
            self.source_path.text() or str(default_data_root() or Path.home()),
            "场景配置 (*.json *.json.bak);;所有文件 (*)")
        if path:
            self._set_source(path)

    def _analyze(self):
        self._invalidate()
        if not self.source_path.text().strip():
            self.status.setText("请先选择直播姬场景配置文件。")
            return
        width, height = self.canvas_width.value(), self.canvas_height.value()
        if bool(width) != bool(height):
            self.status.setText("请同时填写画布宽高，或都设为自动检测。")
            return
        try:
            source = Path(self.source_path.text().strip())
            data = read_config(source)
            self.result = convert_collection(
                data, name=self.collection_name.text(),
                source_dir=source.parent,
                resolution=(width, height) if width else None,
                filter_prefixed_scenes=self.filter_prefixed_scenes.isChecked(),
            )
        except (OSError, ConversionError, RecursionError) as exc:
            self.status.setText(f"分析失败：{exc}")
            return
        self.report.setPlainText(self.result.summary())
        self.export_button.setEnabled(True)
        self.status.setText("预览已生成。导出将保存本次预览的配置快照。")

    def _export(self):
        if self.result is None:
            return
        suggested = Path.home() / f"Livehime-OBS-{datetime.now():%Y%m%d-%H%M%S}.json"
        path, _ = QFileDialog.getSaveFileName(self,
                                              "导出 OBS 场景集合（请选择新文件名）",
                                              str(suggested),
                                              "OBS 场景集合 (*.json)")
        if not path:
            return
        destination = Path(path)
        if not destination.suffix:
            destination = destination.with_suffix(".json")
        try:
            export_collection(self.result, destination)
        except FileExistsError:
            self.status.setText(
                "该文件已存在。为保护原配置，请选择新的导出文件名。")
            return
        except (OSError, ValueError) as exc:
            self.status.setText(f"导出失败：{exc}")
            return
        self.status.setText(f"已导出：{destination}")
        message = QMessageBox(self)
        message.setWindowTitle("配置转换完成")
        message.setTextFormat(Qt.TextFormat.PlainText)
        message.setText(
            f"已导出：{destination}\n\n在 OBS 中选择「场景集合 → 导入」，选择此文件。\n请按预览提示检查被跳过的项目、画布和音频设备。")
        message.setIcon(QMessageBox.Icon.Information)
        message.exec()
