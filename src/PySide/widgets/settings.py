from PySide6.QtCore import Qt, QSize, Slot
from PySide6.QtWidgets import (
    QWidget, QScrollArea, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QRadioButton, QButtonGroup, QCheckBox,
    QPushButton, QFrame, QFileDialog, QFontDialog, QApplication, QSlider
)
from src.models.classes import FocusPlaceholderLineEdit

from src import app_state


class SettingsWidget(QWidget):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

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

    def add_text_item(self, label: str, btn_label: str | list[str],
                      placeholder: str | list[str] = "") -> (
            tuple[FocusPlaceholderLineEdit, QPushButton] |
            list[tuple[FocusPlaceholderLineEdit, QPushButton]]):
        """
        Adds a text item to the user interface consisting of a label and one or more
        editable text fields with corresponding save buttons, all placed in a single row.

        When ``btn_label`` is a single string the method behaves exactly as before and
        returns a ``(FocusPlaceholderLineEdit, QPushButton)`` tuple.

        When ``btn_label`` is a **list** of strings, multiple input+button pairs are
        created side-by-side in one row.  ``placeholder`` should be a list of the same
        length (or a single string applied to every field).  The return value is then a
        ``list[tuple[FocusPlaceholderLineEdit, QPushButton]]``.

        :param label: The text to display as the section title label.
        :param btn_label: Button text(s). A single string for one field, or a list for multiple.
        :param placeholder: Placeholder text(s), matching *btn_label* in length when a list.
        :return: A single (edit, btn) tuple or a list of them when multiple fields are requested.
        """
        single_mode = isinstance(btn_label, str)
        btn_labels: list[str] = [btn_label] if single_mode else list(btn_label)
        if isinstance(placeholder, str):
            placeholders: list[str] = [placeholder] * len(btn_labels)
        else:
            placeholders = list(placeholder)
        if len(placeholders) != len(btn_labels):
            raise ValueError(
                "placeholder list length must match btn_label list length")

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

        results: list[tuple[FocusPlaceholderLineEdit, QPushButton]] = []
        for btn_text, ph in zip(btn_labels, placeholders):
            text_edit = FocusPlaceholderLineEdit()
            text_edit.update_placeholder(ph)

            save_btn = QPushButton(btn_text)
            save_btn.setCursor(Qt.CursorShape.PointingHandCursor)

            # capture per-field references in closure
            def _make_update(te=text_edit):
                @Slot()
                def _update_placeholder():
                    te.update_placeholder(te.text())

                return _update_placeholder

            save_btn.clicked.connect(_make_update())

            row.addWidget(text_edit, 1)
            row.addWidget(save_btn, 0)
            results.append((text_edit, save_btn))

        v.addLayout(row)

        self.main_vbox.addWidget(frame)
        return results[0] if single_mode else results

    def add_multi_choice_item(self, label: str, options: list[str], *,
                              default: int = 0) -> QButtonGroup:
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

    def add_switch_item(self, label: str, checked: bool = False) -> QCheckBox:
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
                             placeholder: str = "") -> tuple[
        QLineEdit, QPushButton]:
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

        @Slot()
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

        @Slot()
        def open_dialog():
            ok, font = QFontDialog.getFont(
                QApplication.font(),  # initial
                self,
                dialog_title,  # title
                options  # options
            )
            if ok:
                font_edit.setText(font.family())
                app_state.app_settings["custom_font"] = font.toString()

        font_btn.clicked.connect(
            open_dialog)

        row.addWidget(font_edit, 1)
        row.addWidget(font_btn, 0)
        v.addLayout(row)

        self.main_vbox.addWidget(frame)
        return font_edit, font_btn

    def add_slider_item(self, label: str, *, min_value: int, max_value: int,
                        default: float, suffix: str = "") -> QSlider:
        """
        通用滑条项：Label + Slider + 当前数值标签。
        返回 QSlider，方便绑定 valueChanged。
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

        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(min_value, max_value)
        slider.setValue(default)

        value_lbl = QLabel(f"{default}{suffix}")
        value_lbl.setFixedWidth(60)

        @Slot(int)
        def _update_value(val: int):
            value_lbl.setText(f"{val}{suffix}")

        slider.valueChanged.connect(_update_value)

        row.addWidget(slider, 1)
        row.addWidget(value_lbl, 0)
        v.addLayout(row)

        self.main_vbox.addWidget(frame)
        return slider
