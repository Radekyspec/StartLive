from PySide6.QtCore import Qt, QSize
from PySide6.QtWidgets import (
    QWidget, QScrollArea, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QRadioButton, QButtonGroup, QCheckBox,
    QPushButton, QFrame, QFileDialog, QFontDialog, QApplication
)

import config


class SettingsPage(QWidget):
    def __init__(self, parent: "MainWindow" = None):
        super().__init__(parent)

        self._parent_window = parent
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        self.main_vbox = QVBoxLayout(container)
        self.main_vbox.setContentsMargins(16, 16, 16, 16)
        self.main_vbox.setSpacing(24)
        scroll.setWidget(container)

        root = QVBoxLayout(self)
        root.addWidget(scroll)

        self.title_font = self.font()
        self.title_font.setPointSize(14)
        self.title_font.setBold(True)

        self.proxy_group = self.add_multi_choice_item(
            "代理设置", ["不使用代理", "使用系统代理"], default=(1 if config.app_settings["use_proxy"] else 0)
        )
        self.proxy_group.idClicked.connect(self._parent_window.switch_proxy)

        self.tray_icon_edit, self.tray_icon_btn = self.add_file_picker_item(
            "自定义托盘图标", dialog_title="选择托盘图标图片",
            name_filter="图片文件 (*.jfif;*.pjpeg;*.jpeg;*.pjp;*.jpg;*.png);;所有文件 (*)",
            placeholder=config.app_settings["custom_tray_icon"]
        )
        self.tray_icon_edit.textChanged.connect(self._parent_window.switch_tray_icon)

        self.font_edit, self.font_btn = self.add_font_picker_item(
            "自定义显示字体（重启生效）", options=(QFontDialog.FontDialogOption.DontUseNativeDialog | QFontDialog.FontDialogOption.ScalableFonts))
        self.main_vbox.addStretch(1)

    def add_section_title(self, text: str):
        frame = QFrame()
        v = QVBoxLayout(frame)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(6)
        lbl = QLabel(text)
        lbl.setFont(self.title_font)
        v.addWidget(lbl)
        self.main_vbox.addWidget(frame)
        return frame

    def add_text_item(self, label: str, placeholder: str = ""):
        """
        Adds a text item to the user interface consisting of a label and an editable text field.
        The label displays the given text, and the text field optionally contains placeholder text.

        :param label: The text to display as the label. This identifies the purpose of the text field.
        :type label: str
        :param placeholder: Optional placeholder text shown in the text field when it is empty.
        :type placeholder: str
        :return: The editable text field (QLineEdit) added to the interface.
        :rtype: QLineEdit
        """
        frame = QFrame()
        v = QVBoxLayout(frame)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(6)
        lbl = QLabel(label)
        lbl.setFont(self.title_font)
        v.addWidget(lbl)
        edit = QLineEdit()
        edit.setPlaceholderText(placeholder)
        v.addWidget(edit)
        self.main_vbox.addWidget(frame)
        return edit

    def add_multi_choice_item(self, label: str, options: list[str], *, default: int = 0):
        """
        Adds a multiple-choice item to the user interface. This method allows the user
        to select from a set of options where one choice is exclusive. The layout
        includes a label describing the choice and a group of radio buttons corresponding
        to the available options.

        :param label: The label or title for the multiple-choice item.
        :type label: str
        :param options: A list of string options for the user to choose from.
        :type options: list[str]
        :param default: The index of the option that should be selected by default.
                        Defaults to 0.
        :type default: int
        :return: Returns the button group that manages the set of radio buttons for
                 the multiple-choice selection.
        :rtype: QButtonGroup
        """
        frame = QFrame()
        v = QVBoxLayout(frame)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(6)
        lbl = QLabel(label)
        lbl.setFont(self.title_font)
        v.addWidget(lbl)
        opts_box = QVBoxLayout()
        opts_box.setSpacing(8)
        group = QButtonGroup(frame)
        group.setExclusive(True)
        for idx, opt in enumerate(options):
            rb = QRadioButton(opt)
            opts_box.addWidget(rb)
            group.addButton(rb, id=idx)
            if idx == default:
                rb.setChecked(True)
        v.addLayout(opts_box)
        self.main_vbox.addWidget(frame)
        return group

    def add_switch_item(self, label: str, checked: bool = False):
        frame = QFrame()
        v = QVBoxLayout(frame)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(6)
        lbl = QLabel(label)
        lbl.setFont(self.title_font)
        v.addWidget(lbl)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        sw = QCheckBox()
        sw.setChecked(checked)
        sw.setCursor(Qt.CursorShape.PointingHandCursor)
        sw.setFixedSize(QSize(52, 28))
        row.addWidget(sw)
        row.addStretch(1)
        v.addLayout(row)
        self.main_vbox.addWidget(frame)
        return sw

    def add_file_picker_item(self, label: str, *, dialog_title="选择文件",
                             name_filter="All Files (*)", start_dir="",
                             placeholder: str = "") -> tuple[QLineEdit, QPushButton]:
        """
        Adds a file picker item to the user interface.

        This method creates a UI component consisting of a label, a read-only text
        field for displaying the file path, and a button for opening a file dialog.
        When the user clicks the button, a file picker dialog is displayed, allowing
        them to select a file. The selected file's path is displayed in the text field.

        :param placeholder: Text to display in the text field when no file is selected.
        :param label: The label text displayed above the file picker.
        :type label: str
        :param dialog_title: The title of the file selection dialog.
                             Defaults to "选择文件".
        :type dialog_title: str, optional
        :param name_filter: The file filter string used in the file selection dialog,
                            e.g., "All Files (*)". Defaults to "All Files (*)".
        :type name_filter: str, optional
        :param start_dir: The starting directory for the file picker dialog.
                          Defaults to an empty string, which indicates the current directory.
        :type start_dir: str, optional
        :return: A tuple containing a QLineEdit and a QPushButton. The QLineEdit is used
                 to display the selected file path, and the QPushButton triggers the file
                 dialog.
        :rtype: tuple[QLineEdit, QPushButton]
        """
        frame = QFrame()
        v = QVBoxLayout(frame)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(6)

        lbl = QLabel(label)
        lbl.setFont(self.title_font)
        v.addWidget(lbl)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)

        path_edit = QLineEdit()
        path_edit.setReadOnly(True)
        path_edit.setPlaceholderText(placeholder)

        pick_btn = QPushButton("选择文件")
        pick_btn.setCursor(Qt.CursorShape.PointingHandCursor)

        def open_dialog():
            path, _ = QFileDialog.getOpenFileName(self, dialog_title, start_dir,
                                                  name_filter)
            if path:
                path_edit.setText(path)

        pick_btn.clicked.connect(
            open_dialog)

        row.addWidget(path_edit, 1)
        row.addWidget(pick_btn, 0)
        v.addLayout(row)

        self.main_vbox.addWidget(frame)
        return path_edit, pick_btn

    def add_font_picker_item(self, label: str, *, dialog_title="选择字体",
                             options
                             ) -> tuple[QLineEdit, QPushButton]:
        frame = QFrame()
        v = QVBoxLayout(frame)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(6)

        lbl = QLabel(label)
        lbl.setFont(self.title_font)
        v.addWidget(lbl)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)

        font_edit = QLineEdit()
        font_edit.setReadOnly(True)
        font_edit.setPlaceholderText(QApplication.font().family())

        font_btn = QPushButton("选择字体")
        font_btn.setCursor(Qt.CursorShape.PointingHandCursor)

        def open_dialog():
            ok, font = QFontDialog.getFont(
                QApplication.font(),  # initial
                self._parent_window,
                dialog_title,  # title
                options  # options
            )
            if ok:
                font_edit.setText(font.family())
                config.app_settings["custom_font"] = font.toString()

        font_btn.clicked.connect(
            open_dialog)

        row.addWidget(font_edit, 1)
        row.addWidget(font_btn, 0)
        v.addLayout(row)

        self.main_vbox.addWidget(frame)
        return font_edit, font_btn

    def reset_default(self):
        self.proxy_group.button(0).setChecked(True)
        self.tray_icon_edit.setText(config.app_settings["custom_tray_icon"])
