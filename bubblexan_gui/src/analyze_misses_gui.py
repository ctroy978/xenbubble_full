"""UI for the Question Miss Analyzer tab."""

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
from PyQt6.QtGui import QDoubleValidator
from PyQt6.QtWidgets import (
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QCheckBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from config import CLI_PATH, PROJECT_ROOT, PYTHON_EXECUTABLE, TEST_BUILD_PATH


class AnalyzeMissesGui(QWidget):
    """Tab that wraps analyze_misses.py."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._script_path = CLI_PATH / "analyze_misses.py"
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

        self.results_input = self._make_file_row(
            form_layout,
            label="Results CSV:",
            tooltip="Responses from the scanner (e.g., output/results.csv).",
            default=str(PROJECT_ROOT / "output" / "results.csv"),
        )

        self.answer_key_input = self._make_file_row(
            form_layout,
            label="Answer Key CSV:",
            tooltip="Answer key with columns Question,Correct_Answer,Points.",
            default=str(PROJECT_ROOT / "output" / "answer_key.csv"),
        )

        self.output_csv_input = self._make_file_row(
            form_layout,
            label="Report CSV:",
            tooltip="Destination for miss_report.csv.",
            default=str(PROJECT_ROOT / "output" / "miss_report.csv"),
            save_dialog=True,
        )

        threshold_validator = QDoubleValidator(0.0, 100.0, 2, self)
        threshold_validator.setNotation(QDoubleValidator.Notation.StandardNotation)
        self.miss_threshold_input = QLineEdit("50")
        self.miss_threshold_input.setValidator(threshold_validator)
        self.miss_threshold_input.setToolTip("Highlight questions missed by at least this percent (0-100).")
        form_layout.addRow("Miss Threshold (%):", self.miss_threshold_input)

        partial_validator = QDoubleValidator(0.0, 1.0, 2, self)
        partial_validator.setNotation(QDoubleValidator.Notation.StandardNotation)
        self.partial_threshold_input = QLineEdit("1.0")
        self.partial_threshold_input.setValidator(partial_validator)
        self.partial_threshold_input.setToolTip("Score multiplier for partial matches (0-1).")
        form_layout.addRow("Partial Threshold:", self.partial_threshold_input)

        self.log_checkbox = QCheckBox("Save log file")
        self.log_checkbox.setToolTip("Enable to capture console details in a log file.")
        self.log_checkbox.toggled.connect(self._toggle_log_inputs)
        log_row = QWidget()
        log_layout = QVBoxLayout(log_row)
        log_layout.setContentsMargins(0, 0, 0, 0)
        log_layout.setSpacing(6)
        log_layout.addWidget(self.log_checkbox)

        log_path_layout = QHBoxLayout()
        self.log_path_input = QLineEdit(str(PROJECT_ROOT / "output" / "miss_report.log"))
        self.log_path_input.setEnabled(False)
        self.log_path_input.setToolTip("Log file path when logging is enabled.")
        log_path_layout.addWidget(self.log_path_input)
        log_browse = QPushButton("Browse…")
        log_browse.setEnabled(False)
        log_browse.setToolTip("Choose a destination for the log file.")
        log_browse.clicked.connect(self._choose_log_file)
        self._log_browse_button = log_browse
        log_path_layout.addWidget(log_browse)

        log_layout.addLayout(log_path_layout)
        form_layout.addRow("Logging:", log_row)

        main_layout.addWidget(
            form_container,
            alignment=Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft,
        )

        self.run_button = QPushButton("Analyze Misses")
        self.run_button.setToolTip("Run the analyzer using the CLI tools.")
        self.run_button.setFixedWidth(220)
        self.run_button.clicked.connect(self._run_analyzer)
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
        self.output_view.setToolTip("Command output, warnings, and generated file paths.")
        output_layout.addWidget(self.output_view)

        main_layout.addWidget(
            output_container,
            alignment=Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft,
        )

        self.review_button = QPushButton("Review Report")
        self.review_button.setToolTip("Open miss_report.csv for review.")
        self.review_button.setFixedWidth(220)
        self.review_button.setEnabled(False)
        self.review_button.clicked.connect(self._open_report)
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
            start_path = line_edit.text().strip() or str(TEST_BUILD_PATH)
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
        start_path = self.log_path_input.text().strip() or str(TEST_BUILD_PATH)
        selected, _ = QFileDialog.getSaveFileName(
            self,
            "Select log file",
            start_path,
            "Log files (*.log);;All files (*)",
        )
        if selected:
            self.log_path_input.setText(selected)

    def _collect_inputs(self) -> dict[str, Path | float | bool]:
        results = Path(self.results_input.text().strip()).expanduser()
        if not results.is_file():
            raise ValueError("Results CSV not found.")

        answer_key = Path(self.answer_key_input.text().strip()).expanduser()
        if not answer_key.is_file():
            raise ValueError("Answer key CSV not found.")

        output_report = Path(self.output_csv_input.text().strip()).expanduser()
        if output_report.is_dir():
            raise ValueError("Report path must be a CSV file.")
        output_report.parent.mkdir(parents=True, exist_ok=True)

        try:
            miss_threshold = float(self.miss_threshold_input.text())
        except ValueError:
            raise ValueError("Miss threshold must be a number between 0 and 100.") from None
        if not (0.0 <= miss_threshold <= 100.0):
            raise ValueError("Miss threshold must be between 0 and 100.")

        try:
            partial_threshold = float(self.partial_threshold_input.text())
        except ValueError:
            raise ValueError("Partial threshold must be a number between 0 and 1.") from None
        if not (0.0 <= partial_threshold <= 1.0):
            raise ValueError("Partial threshold must be between 0 and 1.")

        log_enabled = self.log_checkbox.isChecked()
        log_path = None
        if log_enabled:
            log_path = Path(self.log_path_input.text().strip()).expanduser()
            if log_path.is_dir():
                raise ValueError("Log path must be a file.")
            log_path.parent.mkdir(parents=True, exist_ok=True)

        return {
            "results": results.resolve(),
            "answer_key": answer_key.resolve(),
            "report": output_report.resolve(),
            "miss_threshold": miss_threshold,
            "partial_threshold": partial_threshold,
            "log_enabled": log_enabled,
            "log_path": log_path.resolve() if log_path else None,
        }

    def _run_analyzer(self) -> None:
        try:
            params = self._collect_inputs()
        except ValueError as exc:
            QMessageBox.warning(self, "Check your input", str(exc))
            return

        command = [
            str(PYTHON_EXECUTABLE),
            str(self._script_path),
            "--results",
            str(params["results"]),
            "--key",
            str(params["answer_key"]),
            "--output",
            str(params["report"]),
            "--miss-threshold",
            str(params["miss_threshold"]),
            "--partial-threshold",
            str(params["partial_threshold"]),
        ]
        if params["log_enabled"] and params["log_path"]:
            command.extend(["--log", str(params["log_path"])])

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
                "Analyzer failed",
                "The CLI command reported an error. See the output panel for details.",
            )
        else:
            messages = [result.stdout.strip(), result.stderr.strip()]
            for chunk in messages:
                if chunk:
                    self.output_view.append(chunk + "\n")
            summary = self._format_summary(params)
            self.output_view.append(summary)
            if self._latest_report and self._latest_report.exists():
                self.review_button.setEnabled(True)
        finally:
            self.run_button.setEnabled(True)

    def _format_summary(self, params: dict[str, Path | float | bool]) -> str:
        report_path = params["report"]
        self._latest_report = report_path if isinstance(report_path, Path) else None
        lines = ["Report written to:", str(report_path)]
        if params.get("log_enabled") and params.get("log_path"):
            lines.append(f"Log file: {params['log_path']}")
        return "\n".join(lines)

    def _open_report(self) -> None:
        if not self._latest_report:
            QMessageBox.information(
                self,
                "No report",
                "Run the analyzer first, then review the report.",
            )
            return

        if not self._latest_report.exists():
            QMessageBox.warning(
                self,
                "File missing",
                "The miss report could not be found. Re-run the analyzer.",
            )
            self.review_button.setEnabled(False)
            self._latest_report = None
            return

        target = str(self._latest_report)
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
                "Could not open the report with the default viewer.",
            )
