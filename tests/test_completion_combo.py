import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from src.PySide.classes.completion_combo import CompletionComboBox


class CompletionComboBoxTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_filtering_does_not_mutate_combo_items(self) -> None:
        combo = CompletionComboBox(["Alpha", "Beta", "Alpine"])

        combo.update_completer("alp")

        self.assertEqual(
            [combo.itemText(index) for index in range(combo.count())],
            ["Alpha", "Beta", "Alpine"],
        )
        self.assertEqual(
            combo._completion_model.stringList(),
            ["Alpha", "Alpine"],
        )

    def test_add_items_appends_each_new_item_once(self) -> None:
        combo = CompletionComboBox(["Alpha"])

        combo.addItems(["Beta", "Gamma"])

        expected = ["Alpha", "Beta", "Gamma"]
        self.assertEqual(combo.items, expected)
        self.assertEqual(
            [combo.itemText(index) for index in range(combo.count())],
            expected,
        )
        self.assertEqual(combo._completion_model.stringList(), expected)

    def test_clear_synchronizes_combo_and_completion_models(self) -> None:
        combo = CompletionComboBox(["Alpha", "Beta"])
        combo.update_completer("alp")

        combo.clear()

        self.assertEqual(combo.count(), 0)
        self.assertEqual(combo.items, [])
        self.assertEqual(combo._completion_model.stringList(), [])


if __name__ == "__main__":
    unittest.main()
