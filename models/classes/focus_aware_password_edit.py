from PySide6.QtWidgets import QLineEdit


class FocusAwareLineEdit(QLineEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setEchoMode(
            QLineEdit.EchoMode.Password)  # Start with password mode

    def focusInEvent(self, event):
        super().focusInEvent(event)
        self.setEchoMode(QLineEdit.EchoMode.Normal)  # Reveal text when focused

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self.setEchoMode(
            QLineEdit.EchoMode.Password)  # Hide text when focus is lost
