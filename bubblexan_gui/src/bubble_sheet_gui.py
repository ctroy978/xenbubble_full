"""UI for the Bubble Sheet Generator tab."""

from __future__ import annotations

import shlex
import subprocess
import sys
from pathlib import Path
from typing import TypedDict

SRC_DIR = Path(__file__).resolve().parent
GUI_ROOT = SRC_DIR.parent
if str(GUI_ROOT) not in sys.path:
    sys.path.insert(0, str(GUI_ROOT))

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIntValidator
from PyQt6.QtWidgets import (
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QCheckBox,
    QComboBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from config import CLI_PATH, PROJECT_ROOT, PYTHON_EXECUTABLE


class _FormValues(TypedDict):
    questions: int
    id_length: int
    orientation: str
    border: bool
    output_name: str
    paper_size: str
    output_dir: Path


class BubbleSheetGui(QWidget):
    """Tab that wraps generate_bubblesheet.py."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._script_path = CLI_PATH / "generate_bubblesheet.py"
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

        self.questions_input = QLineEdit("25")
        self.questions_input.setValidator(QIntValidator(1, 50, self))
        self.questions_input.setToolTip("Number of questions for the bubble sheet (1-50).")
        form_layout.addRow("Questions:", self.questions_input)

        self.id_length_input = QLineEdit("6")
        self.id_length_input.setValidator(QIntValidator(4, 10, self))
        self.id_length_input.setToolTip("Digits in the student ID column (4-10).")
        form_layout.addRow("ID Length:", self.id_length_input)

        self.orientation_select = QComboBox()
        self.orientation_select.addItems(["vertical", "horizontal"])
        self.orientation_select.setToolTip("Bubble orientation for the student ID column.")
        form_layout.addRow("ID Orientation:", self.orientation_select)

        self.border_check = QCheckBox("Draw outer border")
        self.border_check.setToolTip("Enable to draw a thick border around the sheet.")
        form_layout.addRow(QLabel("Border:"), self.border_check)

        self.output_name_input = QLineEdit("exam1")
        self.output_name_input.setToolTip("Prefix for the generated files (e.g., exam1).")
        form_layout.addRow("Output Name:", self.output_name_input)

        self.paper_size_select = QComboBox()
        self.paper_size_select.addItems(["A4", "LETTER"])
        self.paper_size_select.setToolTip("Paper size for the PDF.")
        form_layout.addRow("Paper Size:", self.paper_size_select)

        output_dir_container = QWidget()
        output_dir_layout = QVBoxLayout(output_dir_container)
        output_dir_layout.setContentsMargins(0, 0, 0, 0)
        output_dir_layout.setSpacing(6)
        self.output_dir_input = QLineEdit(str(PROJECT_ROOT / "output"))
        self.output_dir_input.setToolTip("Folder where the PDF and layout JSON will be saved.")
        browse_button = QPushButton("Browse for folder…")
        browse_button.setToolTip("Choose a folder for generated files.")
        browse_button.clicked.connect(self._choose_output_dir)
        output_dir_layout.addWidget(self.output_dir_input)
        output_dir_layout.addWidget(browse_button, alignment=Qt.AlignmentFlag.AlignLeft)
        form_layout.addRow("Output Folder:", output_dir_container)

        content_layout.addLayout(form_layout)

        self.run_button = QPushButton("Generate Bubble Sheet")
        self.run_button.setToolTip("Run the generator using the CLI tools.")
        self.run_button.setFixedWidth(220)
        self.run_button.clicked.connect(self._run_generator)
        content_layout.addWidget(
            self.run_button, alignment=Qt.AlignmentFlag.AlignLeft
        )
        main_layout.addWidget(
            content_widget,
            alignment=Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft,
        )

        output_label = QLabel("Command Output")
        output_label.setContentsMargins(0, 10, 0, 0)
        main_layout.addWidget(output_label, alignment=Qt.AlignmentFlag.AlignLeft)

        output_container = QWidget()
        output_layout = QVBoxLayout(output_container)
        output_layout.setContentsMargins(0, 0, 0, 0)
        output_container.setMinimumWidth(720)
        output_container.setMaximumWidth(860)

        self.output_view = QTextEdit()
        self.output_view.setReadOnly(True)
        self.output_view.setMinimumHeight(220)
        self.output_view.setToolTip("Command output and generated file paths.")
        output_layout.addWidget(self.output_view)

        main_layout.addWidget(
            output_container,
            alignment=Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft,
        )

        main_layout.addStretch()

    def _choose_output_dir(self) -> None:
        selected = QFileDialog.getExistingDirectory(
            self, "Select Output Folder", self.output_dir_input.text()
        )
        if selected:
            self.output_dir_input.setText(selected)

    def _collect_inputs(self) -> _FormValues:
        def _parse_int(widget: QLineEdit, low: int, high: int, label: str) -> int:
            try:
                value = int(widget.text())
            except ValueError:
                raise ValueError(f"{label} must be a number between {low} and {high}.") from None
            if not (low <= value <= high):
                raise ValueError(f"{label} must be between {low} and {high}.")
            return value

        questions = _parse_int(self.questions_input, 1, 50, "Questions")
        id_length = _parse_int(self.id_length_input, 4, 10, "ID length")

        output_name = self.output_name_input.text().strip()
        if not output_name:
            raise ValueError("Output name cannot be empty.")

        output_dir = Path(self.output_dir_input.text()).expanduser()
        if not output_dir.is_absolute():
            output_dir = (PROJECT_ROOT / output_dir).resolve()
        output_dir.mkdir(parents=True, exist_ok=True)

        return {
            "questions": questions,
            "id_length": id_length,
            "orientation": self.orientation_select.currentText(),
            "border": self.border_check.isChecked(),
            "output_name": output_name,
            "paper_size": self.paper_size_select.currentText(),
            "output_dir": output_dir,
        }

    def _run_generator(self) -> None:
        try:
            params = self._collect_inputs()
        except ValueError as exc:
            QMessageBox.warning(self, "Check your input", str(exc))
            return

        command = self._build_command(params)
        self.run_button.setEnabled(False)
        self.output_view.clear()
        self.output_view.append(f"$ {shlex.join(command)}\n")

        try:
            result = subprocess.run(
                command,
                check=True,
                capture_output=True,
                text=True,
                cwd=str(CLI_PATH),
            )
        except FileNotFoundError:
            QMessageBox.critical(
                self,
                "Missing executable",
                "Could not find the CLI Python interpreter. Verify bubblexan_cli/.venv exists.",
            )
            return
        except subprocess.CalledProcessError as exc:
            self.output_view.append(exc.stdout)
            self.output_view.append(exc.stderr)
            QMessageBox.critical(
                self,
                "Generator failed",
                "The CLI command reported an error. See the output panel for details.",
            )
        else:
            messages = [result.stdout.strip(), result.stderr.strip()]
            for chunk in messages:
                if chunk:
                    self.output_view.append(chunk + "\n")
            summary = self._format_summary(params)
            self.output_view.append(summary)
        finally:
            self.run_button.setEnabled(True)

    def _build_command(self, params: _FormValues) -> list[str]:
        cmd = [
            str(PYTHON_EXECUTABLE),
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
        if params["border"]:
            cmd.append("--border")
        return cmd

    def _format_summary(self, params: _FormValues) -> str:
        base = params["output_dir"] / params["output_name"]
        expected_files = [
            base.with_suffix(".pdf"),
            params["output_dir"] / f"{params['output_name']}_layout.json",
        ]
        lines = ["Generated files:"]
        lines.extend(str(path) for path in expected_files)
        return "\n".join(lines)
