"""UI for the Grade Adjustment tab."""

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
    QCheckBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from config import CLI_PATH, PROJECT_ROOT, PYTHON_EXECUTABLE


class AdjustGradesGui(QWidget):
    """Tab that wraps adjust_grades.py."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._script_path = CLI_PATH / "adjust_grades.py"
        self._latest_output: Path | None = None
        self._init_ui()

    def _init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 10, 10, 10)

        form_container = QWidget(self)
        form_container.setMaximumWidth(520)
        form_layout = QFormLayout(form_container)
        form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        form_layout.setFormAlignment(Qt.AlignmentFlag.AlignTop)

        self.input_csv_input = self._make_file_row(
            form_layout,
            label="Input CSV:",
            tooltip="Select the graded report CSV to adjust.",
            default=str(PROJECT_ROOT / "output" / "graded_report.csv"),
        )

        self.questions_input = QLineEdit("Q2 Q5")
        self.questions_input.setToolTip("Space-separated question IDs to zero out (e.g., Q2 Q5).")
        form_layout.addRow("Questions to adjust:", self.questions_input)

        self.output_csv_input = self._make_file_row(
            form_layout,
            label="Adjusted CSV:",
            tooltip="Destination CSV for adjusted grades.",
            default=str(PROJECT_ROOT / "output" / "report_adjusted.csv"),
            save_dialog=True,
        )

        self.log_checkbox = QCheckBox("Save log file")
        self.log_checkbox.setToolTip("Enable to save a log of the adjustments.")
        self.log_checkbox.toggled.connect(self._toggle_log_inputs)

        log_container = QWidget()
        log_layout = QVBoxLayout(log_container)
        log_layout.setContentsMargins(0, 0, 0, 0)
        log_layout.setSpacing(6)
        log_layout.addWidget(self.log_checkbox)

        self.log_path_input = QLineEdit(str(PROJECT_ROOT / "output" / "report_adjusted.log"))
        self.log_path_input.setEnabled(False)
        self.log_path_input.setToolTip("Path to log file when logging is enabled.")
        log_layout.addWidget(self.log_path_input)

        log_browse = QPushButton("Browse…")
        log_browse.setEnabled(False)
        log_browse.setToolTip("Choose a destination for the log file.")
        log_browse.clicked.connect(self._choose_log_file)
        self._log_browse_button = log_browse
        log_layout.addWidget(log_browse, alignment=Qt.AlignmentFlag.AlignLeft)

        form_layout.addRow("Logging:", log_container)

        main_layout.addWidget(
            form_container,
            alignment=Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft,
        )

        self.run_button = QPushButton("Adjust Grades")
        self.run_button.setToolTip("Run the adjustment using the CLI tools.")
        self.run_button.setFixedWidth(220)
        self.run_button.clicked.connect(self._run_adjustment)
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
        self.output_view.setToolTip("Command output, diff summary, and file paths.")
        output_layout.addWidget(self.output_view)

        main_layout.addWidget(
            output_container,
            alignment=Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft,
        )

        self.review_button = QPushButton("Review Adjusted Grades")
        self.review_button.setToolTip("Open the adjusted CSV for review.")
        self.review_button.setFixedWidth(220)
        self.review_button.setEnabled(False)
        self.review_button.clicked.connect(self._open_adjusted)
        main_layout.addWidget(self.review_button, alignment=Qt.AlignmentFlag.AlignLeft)

        main_layout.addStretch()

    def _make_file_row(
        self,
        form_layout: QFormLayout,
        *,
        label: str,
        tooltip: str,
        default: str = "",
        save_dialog: bool = False,
    ) -> QLineEdit:
        container = QWidget()
        row_layout = QVBoxLayout(container)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(6)

        line_edit = QLineEdit(default)
        line_edit.setToolTip(tooltip)
        row_layout.addWidget(line_edit)

        button = QPushButton("Browse…")
        button.setToolTip(tooltip)

        def _choose_path() -> None:
            start_path = line_edit.text().strip() or str(PROJECT_ROOT)
            if save_dialog:
                selected, _ = QFileDialog.getSaveFileName(
                    self,
                    "Select output file",
                    start_path,
                    "CSV files (*.csv);;All files (*)",
                )
            else:
                selected, _ = QFileDialog.getOpenFileName(
                    self,
                    "Select CSV file",
                    start_path,
                    "CSV files (*.csv);;All files (*)",
                )
            if selected:
                line_edit.setText(selected)

        button.clicked.connect(_choose_path)
        row_layout.addWidget(button, alignment=Qt.AlignmentFlag.AlignLeft)

        form_layout.addRow(label, container)
        return line_edit

    def _toggle_log_inputs(self, enabled: bool) -> None:
        self.log_path_input.setEnabled(enabled)
        self._log_browse_button.setEnabled(enabled)

    def _choose_log_file(self) -> None:
        start_path = self.log_path_input.text().strip() or str(PROJECT_ROOT)
        selected, _ = QFileDialog.getSaveFileName(
            self,
            "Select log file",
            start_path,
            "Log files (*.log);;All files (*)",
        )
        if selected:
            self.log_path_input.setText(selected)

    def _collect_inputs(self) -> dict[str, Path | list[str] | bool]:
        input_csv = Path(self.input_csv_input.text().strip()).expanduser()
        if not input_csv.is_file():
            raise ValueError("Input CSV not found.")

        questions_str = self.questions_input.text().strip()
        if not questions_str:
            raise ValueError("Enter at least one question ID to adjust.")
        questions = questions_str.split()

        output_csv = Path(self.output_csv_input.text().strip()).expanduser()
        if output_csv.is_dir():
            raise ValueError("Adjusted output must be a file path.")
        output_csv.parent.mkdir(parents=True, exist_ok=True)

        log_enabled = self.log_checkbox.isChecked()
        log_path = None
        if log_enabled:
            log_path = Path(self.log_path_input.text().strip()).expanduser()
            if log_path.is_dir():
                raise ValueError("Log path must be a file.")
            log_path.parent.mkdir(parents=True, exist_ok=True)

        return {
            "input_csv": input_csv.resolve(),
            "questions": questions,
            "output_csv": output_csv.resolve(),
            "log_enabled": log_enabled,
            "log_path": log_path.resolve() if log_path else None,
        }

    def _run_adjustment(self) -> None:
        try:
            params = self._collect_inputs()
        except ValueError as exc:
            QMessageBox.warning(self, "Check your input", str(exc))
            return

        command = [
            str(PYTHON_EXECUTABLE),
            str(self._script_path),
            "--input",
            str(params["input_csv"]),
            "--output",
            str(params["output_csv"]),
            "--questions",
            *params["questions"],
        ]
        if params["log_enabled"] and params["log_path"]:
            command.extend(["--log", str(params["log_path"])])

        self.run_button.setEnabled(False)
        self.review_button.setEnabled(False)
        self._latest_output = None
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
                "Adjustment failed",
                "The CLI command reported an error. See the output panel for details.",
            )
        else:
            messages = [result.stdout.strip(), result.stderr.strip()]
            for chunk in messages:
                if chunk:
                    self.output_view.append(chunk + "\n")
            summary = self._format_summary(params)
            self.output_view.append(summary)
            if self._latest_output and self._latest_output.exists():
                self.review_button.setEnabled(True)
        finally:
            self.run_button.setEnabled(True)

    def _format_summary(self, params: dict[str, Path | list[str] | bool]) -> str:
        output_csv = params["output_csv"]
        self._latest_output = output_csv if isinstance(output_csv, Path) else None
        lines = ["Adjusted grades saved to:", str(output_csv)]
        if params.get("log_enabled") and params.get("log_path"):
            lines.append(f"Log file: {params['log_path']}")
        return "\n".join(lines)

    def _open_adjusted(self) -> None:
        if not self._latest_output:
            QMessageBox.information(
                self,
                "No file",
                "Run the adjustment first, then review the results.",
            )
            return

        if not self._latest_output.exists():
            QMessageBox.warning(
                self,
                "File missing",
                "The adjusted CSV could not be found. Re-run the adjustment.",
            )
            self.review_button.setEnabled(False)
            self._latest_output = None
            return

        target = str(self._latest_output)
        try:
            if sys.platform == "win32":
                subprocess.run(["cmd", "/c", "start", "", target], check=True)
            elif sys.platform == "darwin":
                subprocess.run(["open", target], check=True)
            else:
                subprocess.run(["xdg-open", target], check=True)
        except subprocess.CalledProcessError:
            QMessageBox.critical(
                self,
                "Open failed",
                "Could not open the adjusted CSV with the default viewer.",
            )
