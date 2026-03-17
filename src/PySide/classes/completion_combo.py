from collections.abc import Sequence

from PySide6.QtCore import QStringListModel
from PySide6.QtWidgets import QComboBox, QCompleter


class CompletionComboBox(QComboBox):
    def __init__(self, items: list[str], parent=None):
        super().__init__(parent)
        self.setEditable(True)
        self.items = items.copy()
        self.model = QStringListModel(items)
        self.setModel(self.model)
        self.completer = QCompleter(items, self)
        self.setCompleter(self.completer)
        self.lineEdit().textEdited.connect(self.update_completer)
        super().addItems(items)

    def addItems(self, texts: Sequence[str], /) -> None:
        super().addItems(self.items)
        self.items.extend(texts)
        self.model.setStringList(self.items)

    def clear(self):
        self.items.clear()
        self.model.setStringList([])
        super().clear()

    def update_completer(self, text):
        filtered_items = [item for item in self.items
                          if text.lower() in item.lower()]
        self.completer.model().setStringList(filtered_items)
