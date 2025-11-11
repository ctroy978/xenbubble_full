"""Answer Key Import tab for the Bubblexan Test Manager GUI."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import config
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

_CSV_FILTER = "CSV Files (*.csv)"
_INSTRUCTIONS = """The Answer Key Import tab lets you upload a CSV answer key for a custom test.

CSV Format:
- File name: answer_key.csv on your computer (the app renames it automatically)
- Headers: Question,Correct_Answer,Points
- Question: Unique ID (e.g., Q1) using letters, numbers, underscores, or hyphens
- Correct_Answer: Single letter (a–e) or comma-separated letters (e.g., "b,c,d") for multi-answer
- Points: Positive number (e.g., 2.00, 4.0)

Example:
Question,Correct_Answer,Points
Q1,"b,c,d",4.00
Q2,a,2.00
Q3,b,2.00

Instructions:
1. Select or create a test in the Test Manager tab.
2. Click "Browse" to pick your CSV file.
3. Click "Import Answer Key" to validate and save it.
4. Use "Review Answer Key" to open the saved file.
5. See README.md for detailed formatting guidance.
"""


class AnswerKeyGui(QWidget):
    """Tab that validates and imports manually created answer key CSV files."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._last_csv: Path | None = None
        self._init_ui()

    def _init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 10, 10, 10)

        content_widget = QWidget(self)
        content_widget.setMaximumWidth(520)
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)

        form_layout = QFormLayout()
        form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        form_layout.setFormAlignment(Qt.AlignmentFlag.AlignTop)

        self.csv_input = QLineEdit()
        self.csv_input.setPlaceholderText("Select answer key CSV")
        self.csv_input.setToolTip("Select a CSV file that matches the Bubblexan answer key format.")

        csv_controls = QWidget()
        csv_layout = QHBoxLayout(csv_controls)
        csv_layout.setContentsMargins(0, 0, 0, 0)
        csv_layout.setSpacing(6)
        csv_layout.addWidget(self.csv_input)

        browse_button = QPushButton("Browse…")
        browse_button.setToolTip("Choose a CSV file from your computer.")
        browse_button.clicked.connect(self._choose_csv)
        csv_layout.addWidget(browse_button)

        form_layout.addRow("CSV File:", csv_controls)

        content_layout.addLayout(form_layout)

        button_row = QWidget()
        button_layout = QHBoxLayout(button_row)
        button_layout.setContentsMargins(0, 0, 0, 0)
        button_layout.setSpacing(12)

        self.import_button = QPushButton("Import Answer Key")
        self.import_button.setFixedWidth(200)
        self.import_button.setToolTip("Validate the CSV and copy it into the selected test folder.")
        self.import_button.clicked.connect(self._import_answer_key)
        button_layout.addWidget(self.import_button)

        self.review_button = QPushButton("Review Answer Key")
        self.review_button.setFixedWidth(180)
        self.review_button.setEnabled(False)
        self.review_button.setToolTip("Open the imported CSV using your default viewer.")
        self.review_button.clicked.connect(self._review_answer_key)
        button_layout.addWidget(self.review_button)

        self.instructions_button = QPushButton("Show Instructions")
        self.instructions_button.setFixedWidth(180)
        self.instructions_button.setToolTip("Display formatting tips and workflow instructions.")
        self.instructions_button.clicked.connect(self._show_instructions)
        button_layout.addWidget(self.instructions_button)

        content_layout.addWidget(button_row, alignment=Qt.AlignmentFlag.AlignLeft)

        main_layout.addWidget(
            content_widget,
            alignment=Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft,
        )

        output_label = QLabel("Status")
        output_label.setContentsMargins(0, 10, 0, 0)
        main_layout.addWidget(output_label, alignment=Qt.AlignmentFlag.AlignLeft)

        output_container = QWidget(self)
        output_layout = QVBoxLayout(output_container)
        output_layout.setContentsMargins(0, 0, 0, 0)
        output_container.setMinimumWidth(720)
        output_container.setMaximumWidth(860)

        self.output_view = QTextEdit()
        mono = QFont("Courier New", 11)
        self.output_view.setFont(mono)
        self.output_view.setReadOnly(True)
        self.output_view.setMinimumHeight(220)
        self.output_view.setToolTip("Import results, instructions, and error details.")
        output_layout.addWidget(self.output_view)

        main_layout.addWidget(
            output_container,
            alignment=Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft,
        )

        main_layout.addStretch()

    def _choose_csv(self) -> None:
        selected, _ = QFileDialog.getOpenFileName(
            self,
            "Select Answer Key CSV",
            filter=_CSV_FILTER,
        )
        if selected:
            self.csv_input.setText(selected)

    def _show_instructions(self) -> None:
        self.output_view.clear()
        self.output_view.setPlainText(_INSTRUCTIONS)

    def _import_answer_key(self) -> None:
        active_folder = config.active_test_folder()
        if not active_folder:
            QMessageBox.warning(
                self,
                "Select a test",
                "Create or select a test in the Test Manager tab before importing an answer key.",
            )
            return

        csv_path = Path(self.csv_input.text().strip()).expanduser()
        if not csv_path:
            QMessageBox.warning(self, "Missing file", "Choose a CSV file to import.")
            return
        if not csv_path.exists():
            QMessageBox.warning(self, "Missing file", f"File '{csv_path}' does not exist.")
            return

        errors = config.validate_answer_key(csv_path)
        if errors:
            QMessageBox.critical(
                self,
                "Invalid CSV format",
                "\n".join(errors),
            )
            return

        exam_title = config.extract_exam_title()
        if not exam_title:
            QMessageBox.warning(
                self,
                "Missing test name",
                "Could not determine the test name. Reselect the test in Test Manager and try again.",
            )
            return

        expected_name = f"{exam_title}_answer_key.csv"
        tests_dir = active_folder / "tests"
        tests_dir.mkdir(parents=True, exist_ok=True)
        destination = tests_dir / expected_name

        try:
            shutil.copy2(csv_path, destination)
        except OSError as exc:  # noqa: PERF203
            QMessageBox.critical(
                self,
                "Copy failed",
                f"Could not copy the file: {exc}",
            )
            return

        message = f"Answer key imported: {destination}"
        self.output_view.append(message)
        self._last_csv = destination
        self.review_button.setEnabled(True)

    def _review_answer_key(self) -> None:
        if not self._last_csv or not self._last_csv.exists():
            QMessageBox.information(
                self,
                "File not found",
                "Import an answer key first so there is a file to review.",
            )
            return

        try:
            if sys.platform.startswith("win"):
                subprocess.Popen(["cmd", "/c", "start", "", str(self._last_csv)])
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(self._last_csv)])
            else:
                subprocess.Popen(["xdg-open", str(self._last_csv)])
        except OSError as exc:  # noqa: PERF203
            QMessageBox.critical(
                self,
                "Viewer error",
                f"Could not open the answer key: {exc}",
            )
