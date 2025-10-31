from collections.abc import Sequence
from typing import Any

from PySide6.QtCore import QStringListModel
from PySide6.QtWidgets import QComboBox, QCompleter


class CompletionComboBox(QComboBox):
    def __init__(self, items: list[str], parent=None):
        super().__init__(parent)
        self.setEditable(True)
        self.items = set(items.copy())
        self.model = QStringListModel(items)
        self.setModel(self.model)
        self.completer = QCompleter(items, self)
        self.setCompleter(self.completer)
        self.lineEdit().textEdited.connect(self.update_completer)
        super().addItems(items)

    def addItem(self, text: str, /, userData: Any = ...) -> None:
        self.items.add(text)
        updated_texts = list(self.items)
        self.model.setStringList(updated_texts)
        super().clear()
        super().addItems(updated_texts)

    def addItems(self, texts: Sequence[str], /) -> None:
        self.items.update(texts)
        updated_texts = list(self.items)
        self.model.setStringList(updated_texts)
        super().clear()
        super().addItems(updated_texts)

    def clear(self):
        super().clear()
        self.items.clear()
        self.model.setStringList([])

    def update_completer(self, text):
        filtered_items = [item for item in self.items
                          if text.lower() in item.lower()]
        self.completer.model().setStringList(filtered_items)
