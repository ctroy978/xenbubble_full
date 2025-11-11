"""Bubble Sheet Generator tab for the Bubblexan Test Manager GUI."""

from __future__ import annotations

import shlex
import subprocess
import sys
from pathlib import Path
from typing import TypedDict

import config
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIntValidator, QFont, QShowEvent
from PyQt6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class _FormValues(TypedDict):
    questions: int
    id_length: int
    orientation: str
    paper_size: str
    output_dir: Path
    output_name: str
    pdf_path: Path
    json_path: Path


class BubbleSheetGui(QWidget):
    """Tab that wraps bubblexan_cli/generate_bubblesheet.py."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        config.validate_cli_environment(["generate_bubblesheet.py"])
        self._script_path = config.CLI_PATH / "generate_bubblesheet.py"
        self._last_pdf_path: Path | None = None
        self._init_ui()
        self._refresh_existing_output()

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

        self.questions_input = QLineEdit("25")
        self.questions_input.setValidator(QIntValidator(1, 50, self))
        self.questions_input.setToolTip("Number of questions (1–50).")
        form_layout.addRow("Questions:", self.questions_input)

        self.id_length_input = QLineEdit("7")
        self.id_length_input.setValidator(QIntValidator(4, 10, self))
        self.id_length_input.setToolTip("Student ID length (4–10).")
        form_layout.addRow("ID Length:", self.id_length_input)

        self.orientation_select = QComboBox()
        self.orientation_select.addItems(["Vertical", "Horizontal"])
        self.orientation_select.setToolTip("Arrange ID digits vertically or horizontally.")
        form_layout.addRow("ID Orientation:", self.orientation_select)

        self.paper_size_select = QComboBox()
        self.paper_size_select.addItems(["A4", "LETTER"])
        self.paper_size_select.setToolTip("Paper size for the bubble sheet.")
        form_layout.addRow("Paper Size:", self.paper_size_select)

        content_layout.addLayout(form_layout)

        self.generate_button = QPushButton("Generate Bubble Sheet")
        self.generate_button.setToolTip("Run the CLI tool to generate the PDF and layout JSON.")
        self.generate_button.setFixedWidth(220)
        self.generate_button.clicked.connect(self._run_generator)
        content_layout.addWidget(
            self.generate_button,
            alignment=Qt.AlignmentFlag.AlignLeft,
        )

        self.review_button = QPushButton("Review Bubble Sheet")
        self.review_button.setToolTip("Open the generated PDF in your default viewer.")
        self.review_button.setFixedWidth(220)
        self.review_button.setEnabled(False)
        self.review_button.clicked.connect(self._review_pdf)
        content_layout.addWidget(
            self.review_button,
            alignment=Qt.AlignmentFlag.AlignLeft,
        )

        main_layout.addWidget(
            content_widget,
            alignment=Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft,
        )

        output_label = QLabel("Command Output")
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
        self.output_view.setToolTip("CLI output and generated file paths.")
        output_layout.addWidget(self.output_view)

        main_layout.addWidget(
            output_container,
            alignment=Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft,
        )

        main_layout.addStretch()

    def _review_pdf(self) -> None:
        self._refresh_existing_output()
        if not self._last_pdf_path or not self._last_pdf_path.exists():
            QMessageBox.information(
                self,
                "File not found",
                "Generate a bubble sheet first so there is a PDF to review.",
            )
            return

        try:
            if sys.platform.startswith("win"):
                subprocess.Popen(["cmd", "/c", "start", "", str(self._last_pdf_path)])
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(self._last_pdf_path)])
            else:
                subprocess.Popen(["xdg-open", str(self._last_pdf_path)])
        except OSError as exc:  # noqa: PERF203
            QMessageBox.critical(
                self,
                "Viewer error",
                f"Could not open the PDF viewer: {exc}",
            )

    def _collect_inputs(self) -> _FormValues:
        active_folder = config.active_test_folder()
        if not active_folder:
            raise ValueError("No test selected. Please select a test in the Test Manager tab.")

        title = config.extract_exam_title()
        if not title:
            raise ValueError("Could not determine the exam title from the selected test.")

        def _parse_int(widget: QLineEdit, low: int, high: int, label: str) -> int:
            try:
                value = int(widget.text())
            except ValueError as exc:  # noqa: PERF203
                raise ValueError(f"{label} must be a number between {low} and {high}.") from exc
            if not (low <= value <= high):
                raise ValueError(f"{label} must be between {low} and {high}.")
            return value

        questions = _parse_int(self.questions_input, 1, 50, "Questions")
        id_length = _parse_int(self.id_length_input, 4, 10, "ID Length")

        orientation = self.orientation_select.currentText().strip().lower()
        if orientation not in {"vertical", "horizontal"}:
            raise ValueError("Orientation must be vertical or horizontal.")

        paper_size = self.paper_size_select.currentText().strip().upper()
        if paper_size not in {"A4", "LETTER"}:
            raise ValueError("Paper size must be A4 or LETTER.")

        output_dir = active_folder / "bubble_sheets"
        output_dir.mkdir(parents=True, exist_ok=True)

        pdf_path = output_dir / f"{title}.pdf"
        json_path = output_dir / f"{title}_layout.json"

        return {
            "questions": questions,
            "id_length": id_length,
            "orientation": orientation,
            "paper_size": paper_size,
            "output_dir": output_dir,
            "output_name": title,
            "pdf_path": pdf_path,
            "json_path": json_path,
        }

    def _run_generator(self) -> None:
        try:
            params = self._collect_inputs()
        except ValueError as exc:
            QMessageBox.warning(self, "Check your inputs", str(exc))
            return

        command = self._build_command(params)
        self.generate_button.setEnabled(False)
        self.review_button.setEnabled(False)
        self.output_view.clear()
        self.output_view.append(f"$ {shlex.join(command)}\n")

        had_previous_pdf = self._last_pdf_path and self._last_pdf_path.exists()
        success = False
        try:
            result = subprocess.run(
                command,
                check=True,
                capture_output=True,
                text=True,
                cwd=str(config.CLI_PATH),
            )
        except FileNotFoundError:
            QMessageBox.critical(
                self,
                "Missing executable",
                "Could not find the CLI Python interpreter. Verify bubblexan_cli/.venv exists.",
            )
            return
        except subprocess.CalledProcessError as exc:
            if exc.stdout:
                self.output_view.append(exc.stdout)
            if exc.stderr:
                self.output_view.append(exc.stderr)
            QMessageBox.critical(
                self,
                "Generator failed",
                "The CLI command reported an error. See the output panel for details.",
            )
        else:
            for chunk in (result.stdout.strip(), result.stderr.strip()):
                if chunk:
                    self.output_view.append(chunk + "\n")
            summary = self._format_summary(params)
            self.output_view.append(summary)
            self._last_pdf_path = params["pdf_path"]
            self.review_button.setEnabled(True)
            success = True
        finally:
            self.generate_button.setEnabled(True)
            if not success and had_previous_pdf:
                self.review_button.setEnabled(True)

    def _build_command(self, params: _FormValues) -> list[str]:
        cmd = [
            str(config.PYTHON_EXECUTABLE),
            str(self._script_path),
            "--questions",
            str(params["questions"]),
            "--id-length",
            str(params["id_length"]),
            "--id-orientation",
            params["orientation"],
            "--output",
            params["output_name"],
            "--paper-size",
            params["paper_size"],
            "--output-dir",
            str(params["output_dir"]),
        ]
        return cmd

    def _format_summary(self, params: _FormValues) -> str:
        lines = [
            "Generated files:",
            str(params["pdf_path"]),
            str(params["json_path"]),
        ]
        return "\n".join(lines)

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._refresh_existing_output()

    def _refresh_existing_output(self) -> None:
        """Check if a bubble sheet already exists for the selected test."""

        active_name = config.ACTIVE_TEST_NAME
        active_folder = config.active_test_folder()
        title = config.extract_exam_title()

        if not active_folder or not title:
            self._last_pdf_path = None
            self.review_button.setEnabled(False)
            return

        candidate = active_folder / "bubble_sheets" / f"{title}.pdf"
        if candidate.exists():
            self._last_pdf_path = candidate
            self.review_button.setEnabled(True)
        else:
            self._last_pdf_path = None
            self.review_button.setEnabled(False)
