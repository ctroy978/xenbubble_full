"""Entry point for the Bubblexan GUI."""

from __future__ import annotations

import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SRC_DIR.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from PyQt6.QtWidgets import QApplication, QMainWindow, QTabWidget

from bubble_sheet_gui import BubbleSheetGui
from qti_test_gui import QtiTestGui
from pdf_to_png_gui import PdfToPngGui
from scanner_gui import ScannerGui
from grade_gui import GradeGui
from analyze_misses_gui import AnalyzeMissesGui
from adjust_grades_gui import AdjustGradesGui
from test_manager_gui import TestManagerGui


class BubblexanWindow(QMainWindow):
    """Main window hosting all tool tabs."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Bubblexan")
        self.resize(800, 600)
        self._init_ui()

    def _init_ui(self) -> None:
        tabs = QTabWidget()
        tabs.addTab(BubbleSheetGui(self), "Bubble Sheet Generator")
        tabs.addTab(QtiTestGui(self), "QTI Test Generator")
        tabs.addTab(PdfToPngGui(self), "PDF → PNG Converter")
        tabs.addTab(ScannerGui(self), "Bubble Sheet Scanner")
        tabs.addTab(GradeGui(self), "Grading")
        tabs.addTab(AnalyzeMissesGui(self), "Question Miss Analyzer")
        tabs.addTab(AdjustGradesGui(self), "Grade Adjustment")
        tabs.addTab(TestManagerGui(self), "Test Manager")
        self.setCentralWidget(tabs)


def main() -> None:
    """Bootstraps the Qt application."""
    app = QApplication(sys.argv)
    window = BubblexanWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
