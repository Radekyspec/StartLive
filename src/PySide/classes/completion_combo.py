from collections.abc import Sequence

from PySide6.QtCore import QStringListModel
from PySide6.QtWidgets import QComboBox, QCompleter


class CompletionComboBox(QComboBox):
    def __init__(self, items: list[str], parent=None):
        super().__init__(parent)
        self.setEditable(True)
        self.items = items.copy()
        self._completion_model = QStringListModel(items, self)
        self.setModel(self._completion_model)
        self._completion_completer = QCompleter(self._completion_model, self)
        self.setCompleter(self._completion_completer)
        line_edit = self.lineEdit()
        if line_edit is not None:
            line_edit.textEdited.connect(self.update_completer)
        super().addItems(items)

    def addItems(self, texts: Sequence[str], /) -> None:
        super().addItems(self.items)
        self.items.extend(texts)
        self._completion_model.setStringList(self.items)

    def clear(self):
        self.items.clear()
        self._completion_model.setStringList([])
        super().clear()

    def update_completer(self, text):
        filtered_items = [item for item in self.items
                          if text.lower() in item.lower()]
        self._completion_model.setStringList(filtered_items)
