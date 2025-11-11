"""Entry point for the Bubblexan Test Manager GUI."""

from __future__ import annotations

import sys
from pathlib import Path

from typing import Optional

from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QApplication, QMainWindow, QMessageBox, QTabWidget, QWidget

SRC_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SRC_DIR.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import config
from answer_key_gui import AnswerKeyGui
from bubble_sheet_gui import BubbleSheetGui
from pdf_to_png_gui import PdfToPngGui
from qti_test_gui import QtiTestGui
from test_manager_gui import TestManagerGui


class BubblexanTabWidget(QTabWidget):
    """Tab widget that enforces selecting a test before other tabs open."""

    def __init__(self) -> None:
        super().__init__()
        self._default_tab: Optional[QWidget] = None
        self._requires_test: dict[QWidget, bool] = {}
        self.currentChanged.connect(self._handle_tab_change)

    def add_managed_tab(self, widget: QWidget, title: str, *, requires_test: bool) -> int:
        index = self.addTab(widget, title)
        self._requires_test[widget] = requires_test
        if not requires_test and self._default_tab is None:
            self._default_tab = widget
        return index

    def _handle_tab_change(self, index: int) -> None:
        if index < 0:
            return
        widget = self.widget(index)
        if not self._requires_test.get(widget, False):
            return
        if config.ACTIVE_TEST_NAME:
            return
        QMessageBox.warning(
            self,
            "Select a test",
            "Create or select a test in the Test Manager tab before opening other tools.",
        )
        if self._default_tab:
            self.blockSignals(True)
            self.setCurrentWidget(self._default_tab)
            self.blockSignals(False)


class BubblexanWindow(QMainWindow):
    """Main window hosting the Test Manager tab."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Bubblexan")
        self.resize(860, 600)
        self._init_ui()

    def _init_ui(self) -> None:
        tabs = BubblexanTabWidget()
        tabs.add_managed_tab(TestManagerGui(self), "Test Manager", requires_test=False)
        tabs.add_managed_tab(BubbleSheetGui(self), "Bubble Sheet Generator", requires_test=True)
        tabs.add_managed_tab(QtiTestGui(self), "QTI Test Generator", requires_test=True)
        tabs.add_managed_tab(AnswerKeyGui(self), "Answer Key Import", requires_test=True)
        tabs.add_managed_tab(PdfToPngGui(self), "PDF to PNG Conversion", requires_test=True)
        self.setCentralWidget(tabs)


def main() -> None:
    """Boot the Qt application."""

    app = QApplication(sys.argv)
    font = QFont("Arial", 12)
    app.setFont(font)
    window = BubblexanWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
