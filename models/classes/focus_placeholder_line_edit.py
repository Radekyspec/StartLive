from PySide6.QtWidgets import QLineEdit


class FocusPlaceholderLineEdit(QLineEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._ph = ""

    def focusInEvent(self, event):
        super().focusInEvent(event)
        self._ph = self.placeholderText()
        self.setPlaceholderText("")

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self.setPlaceholderText(self._ph)

    def update_placeholder(self, text):
        self._ph = text
        self.setPlaceholderText(text)
