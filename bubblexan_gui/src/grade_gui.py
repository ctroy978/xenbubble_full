"""UI for the Grading tab."""

from __future__ import annotations

import shlex
import subprocess
import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent
GUI_ROOT = SRC_DIR.parent
if str(GUI_ROOT) not in sys.path:
    sys.path.insert(0, str(GUI_ROOT))

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFileDialog,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from config import CLI_PATH, PROJECT_ROOT, PYTHON_EXECUTABLE


class GradeGui(QWidget):
    """Tab that wraps grade.py."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._script_path = CLI_PATH / "grade.py"
        self._latest_report: Path | None = None
        self._init_ui()

    def _init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 10, 10, 10)

        form_container = QWidget(self)
        form_container.setMaximumWidth(520)
        form_layout = QFormLayout(form_container)
        form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        form_layout.setFormAlignment(Qt.AlignmentFlag.AlignTop)

        self.results_input = self._make_path_row(
            form_layout,
            label="Results CSV:",
            tooltip="Select the responses CSV from the scanner.",
            button_text="Browse…",
            default=str(PROJECT_ROOT / "output" / "results.csv"),
            filter_text="CSV files (*.csv);;All files (*)",
        )

        self.answer_key_input = self._make_path_row(
            form_layout,
            label="Answer Key CSV:",
            tooltip="Select the answer key CSV (Question,Correct_Answer,Points).",
            button_text="Browse…",
            default=str(PROJECT_ROOT / "output" / "answer_key.csv"),
            filter_text="CSV files (*.csv);;All files (*)",
        )

        self.output_dir_input = self._make_directory_row(
            form_layout,
            label="Output Folder:",
            tooltip="Folder for graded_report.csv/xlsx.",
            default=str(PROJECT_ROOT / "output"),
        )

        main_layout.addWidget(
            form_container,
            alignment=Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft,
        )

        self.run_button = QPushButton("Grade Tests")
        self.run_button.setToolTip("Run the grader using the CLI tools.")
        self.run_button.setFixedWidth(220)
        self.run_button.clicked.connect(self._run_grader)
        main_layout.addWidget(self.run_button, alignment=Qt.AlignmentFlag.AlignLeft)

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

        self.review_button = QPushButton("Review Grades")
        self.review_button.setToolTip("Open graded_report.xlsx (or .csv) for review.")
        self.review_button.setFixedWidth(220)
        self.review_button.setEnabled(False)
        self.review_button.clicked.connect(self._open_report)
        main_layout.addWidget(self.review_button, alignment=Qt.AlignmentFlag.AlignLeft)

        main_layout.addStretch()

    def _make_path_row(
        self,
        form_layout: QFormLayout,
        *,
        label: str,
        tooltip: str,
        button_text: str,
        default: str = "",
        filter_text: str = "All files (*)",
    ) -> QLineEdit:
        container = QWidget()
        row_layout = QVBoxLayout(container)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(6)

        line_edit = QLineEdit(default)
        line_edit.setToolTip(tooltip)
        row_layout.addWidget(line_edit)

        button = QPushButton(button_text)
        button.setToolTip(tooltip)

        def _choose_file() -> None:
            start_dir = line_edit.text().strip() or str(PROJECT_ROOT)
            selected, _ = QFileDialog.getOpenFileName(
                self,
                "Select file",
                start_dir,
                filter_text,
            )
            if selected:
                line_edit.setText(selected)

        button.clicked.connect(_choose_file)
        row_layout.addWidget(button, alignment=Qt.AlignmentFlag.AlignLeft)

        form_layout.addRow(label, container)
        return line_edit

    def _make_directory_row(
        self,
        form_layout: QFormLayout,
        *,
        label: str,
        tooltip: str,
        default: str,
    ) -> QLineEdit:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        line_edit = QLineEdit(default)
        line_edit.setToolTip(tooltip)
        layout.addWidget(line_edit)

        button = QPushButton("Browse for folder…")
        button.setToolTip(tooltip)

        def _choose_dir() -> None:
            start_dir = line_edit.text().strip() or str(PROJECT_ROOT)
            selected = QFileDialog.getExistingDirectory(
                self,
                "Select folder",
                start_dir,
            )
            if selected:
                line_edit.setText(selected)

        button.clicked.connect(_choose_dir)
        layout.addWidget(button, alignment=Qt.AlignmentFlag.AlignLeft)

        form_layout.addRow(label, container)
        return line_edit

    def _collect_inputs(self) -> dict[str, Path]:
        results = Path(self.results_input.text().strip()).expanduser()
        if not results.is_file():
            raise ValueError("Results CSV not found.")

        answer_key = Path(self.answer_key_input.text().strip()).expanduser()
        if not answer_key.is_file():
            raise ValueError("Answer key CSV not found.")

        output_dir = Path(self.output_dir_input.text().strip()).expanduser()
        if not output_dir.is_absolute():
            output_dir = (PROJECT_ROOT / output_dir).resolve()
        output_dir.mkdir(parents=True, exist_ok=True)

        return {
            "results": results.resolve(),
            "answer_key": answer_key.resolve(),
            "output_dir": output_dir,
        }

    def _run_grader(self) -> None:
        try:
            params = self._collect_inputs()
        except ValueError as exc:
            QMessageBox.warning(self, "Check your input", str(exc))
            return

        command = [
            str(PYTHON_EXECUTABLE),
            str(self._script_path),
            str(params["results"]),
            str(params["answer_key"]),
            "--output-dir",
            str(params["output_dir"]),
        ]

        self.run_button.setEnabled(False)
        self.review_button.setEnabled(False)
        self._latest_report = None
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
                "Grading failed",
                "The CLI command reported an error. See the output panel for details.",
            )
        else:
            messages = [result.stdout.strip(), result.stderr.strip()]
            for chunk in messages:
                if chunk:
                    self.output_view.append(chunk + "\n")
            summary = self._format_summary(params["output_dir"])
            self.output_view.append(summary)
            if self._latest_report:
                self.review_button.setEnabled(True)
        finally:
            self.run_button.setEnabled(True)

    def _format_summary(self, output_dir: Path) -> str:
        csv_path = output_dir / "graded_report.csv"
        xlsx_path = output_dir / "graded_report.xlsx"

        self._latest_report = xlsx_path if xlsx_path.exists() else csv_path if csv_path.exists() else None
        lines = ["Generated reports:"]
        lines.append(str(csv_path))
        lines.append(str(xlsx_path))
        if not self._latest_report:
            lines.append("Reports not found yet. Check grader output.")
        return "\n".join(lines)

    def _open_report(self) -> None:
        if not self._latest_report:
            QMessageBox.information(
                self,
                "No report",
                "Run the grader first, then review the results.",
            )
            return

        if not self._latest_report.exists():
            QMessageBox.warning(
                self,
                "File missing",
                "The graded report could not be found. Re-run the grader.",
            )
            self.review_button.setEnabled(False)
            self._latest_report = None
            return

        path_to_open = str(self._latest_report)
        try:
            if sys.platform == "win32":
                subprocess.run(["cmd", "/c", "start", "", path_to_open], check=True)
            elif sys.platform == "darwin":
                subprocess.run(["open", path_to_open], check=True)
            else:
                subprocess.run(["xdg-open", path_to_open], check=True)
        except subprocess.CalledProcessError:
            QMessageBox.critical(
                self,
                "Open failed",
                "Could not open the graded report with the default viewer.",
            )
