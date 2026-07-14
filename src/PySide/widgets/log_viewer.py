from PySide6.QtCore import Slot
from PySide6.QtWidgets import QPlainTextEdit, QVBoxLayout
from PySide6.QtWidgets import QWidget


class LogViewer(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.text = QPlainTextEdit(readOnly=True)
        self.text.setMaximumBlockCount(100)
        self.follow_tail = True
        layout = QVBoxLayout(self)
        layout.addWidget(self.text)
        fm = self.text.fontMetrics()
        self._bottom_epsilon = max(2, fm.lineSpacing())
        sb = self.text.verticalScrollBar()
        sb.valueChanged.connect(self._on_scroll_value_changed)
        sb.rangeChanged.connect(self._on_range_changed)

    @Slot(str)
    def append_line(self, line: str):
        self.text.appendPlainText(line + "\n")
        if self.follow_tail:
            self._scroll_to_bottom()

    @Slot(int)
    def _on_scroll_value_changed(self, value: int):
        sb = self.text.verticalScrollBar()
        self.follow_tail = (sb.maximum() - value) <= self._bottom_epsilon

    @Slot(int, int)
    def _on_range_changed(self, _min: int, _max: int):
        self._on_scroll_value_changed(self.text.verticalScrollBar().value())
        if self.follow_tail:
            self._scroll_to_bottom()

    def _scroll_to_bottom(self):
        sb = self.text.verticalScrollBar()
        sb.setValue(sb.maximum())
