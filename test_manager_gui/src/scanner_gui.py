"""Bubble Sheet Scanner tab for the Bubblexan Test Manager GUI."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import config
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QDoubleValidator, QFont, QShowEvent
from PyQt6.QtWidgets import (
    QCheckBox,
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

_MISSING_PNG_MESSAGE = """No PNGs found in scanned_images/. You may have missed a step:
1. Use the PDF to PNG Conversion tab to convert your scanned PDF to PNGs.
2. Or, check "Use custom PNGs" to import your own PNG files.
Warning: Custom scans must be PNG files for scanning to work.
"""

_CUSTOM_WARNING = "Custom scans must be PNG files for scanning to work."

_TIPS_TEXT = """The Bubble Sheet Scanner tab processes PNG images of scanned bubble sheets to extract student answers, producing a results CSV for grading.

Workflow:
1. Scan bubble sheets as one multi-page PDF (one page per student, 300 DPI, grayscale) using your scanner’s ADF.
2. Use the PDF to PNG Conversion tab to convert the PDF to PNGs, saved in scanned_images/.
3. The app automatically uses PNGs from scanned_images/. To use custom PNGs, check "Use custom PNGs" and browse.
4. Click "Scan Bubble Sheets" to generate results.csv.
5. Review the results CSV and optional log.

Tips:
- Ensure borders and alignment markers are visible in every scan.
- Use #2 pencils and fully fill the bubbles.
- Avoid staples, tape, or lamination.
- Warning: Custom scans must be PNG files for scanning to work.
- If alignment issues occur, run testvision.py (CLI) to debug a single image.
"""


class ScannerGui(QWidget):
    """Tab that wraps bubblexan_cli/scan_bubblesheet.py."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        config.validate_cli_environment(["scan_bubblesheet.py"])
        self._script_path = config.CLI_PATH / "scan_bubblesheet.py"
        self._results_csv: Path | None = None
        self._results_log: Path | None = None
        self._source_path: Path | None = None
        self._layout_path: Path | None = None
        self._init_ui()
        self._evaluate_source_state(show_message=True)
        self._refresh_existing_outputs()

    def _init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 10, 10, 10)

        content_widget = QWidget(self)
        content_widget.setMaximumWidth(620)
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)

        form_layout = QFormLayout()
        form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        form_layout.setFormAlignment(Qt.AlignmentFlag.AlignTop)

        self.default_path_display = QLineEdit()
        self.default_path_display.setReadOnly(True)
        self.default_path_display.setToolTip("PNGs from PDF to PNG Conversion are read automatically from scanned_images/.")
        form_layout.addRow("Default PNGs:", self.default_path_display)

        self.custom_checkbox = QCheckBox("Use custom PNGs")
        self.custom_checkbox.setToolTip(f"Select a different PNG file or folder. Warning: {_CUSTOM_WARNING}")
        self.custom_checkbox.stateChanged.connect(self._handle_custom_toggle)
        form_layout.addRow("", self.custom_checkbox)

        self.custom_input = QLineEdit()
        self.custom_input.setPlaceholderText("Browse for custom PNG, folder, or ZIP")
        self.custom_input.setToolTip(f"Select PNG images, a folder, or ZIP archive of scanned bubble sheets. {_CUSTOM_WARNING}")
        self.custom_input.setEnabled(False)
        self.custom_input.textChanged.connect(lambda _: self._evaluate_source_state(show_message=True))

        custom_controls = QWidget()
        custom_layout = QHBoxLayout(custom_controls)
        custom_layout.setContentsMargins(0, 0, 0, 0)
        custom_layout.setSpacing(6)
        custom_layout.addWidget(self.custom_input)

        self.custom_browse = QPushButton("Browse…")
        self.custom_browse.setEnabled(False)
        self.custom_browse.setToolTip("Choose PNG images, a folder, or ZIP archive. Custom scans must be PNG files.")
        self.custom_browse.clicked.connect(self._choose_custom_path)
        custom_layout.addWidget(self.custom_browse)

        form_layout.addRow("Custom Source:", custom_controls)

        self.threshold_input = QLineEdit("0.5")
        threshold_validator = QDoubleValidator(0.0, 1.0, 3, self)
        threshold_validator.setNotation(QDoubleValidator.Notation.StandardNotation)
        self.threshold_input.setValidator(threshold_validator)
        self.threshold_input.setToolTip("Bubble fill detection threshold (0.0–1.0). Default: 0.5")
        form_layout.addRow("Threshold:", self.threshold_input)

        self.log_checkbox = QCheckBox("Generate log file (results.log)")
        self.log_checkbox.setChecked(True)
        self.log_checkbox.setToolTip("Enable to capture processing warnings in results.log.")
        form_layout.addRow(QLabel("Log Output:"), self.log_checkbox)

        content_layout.addLayout(form_layout)

        button_row = QWidget()
        button_layout = QHBoxLayout(button_row)
        button_layout.setContentsMargins(0, 0, 0, 0)
        button_layout.setSpacing(12)

        self.scan_button = QPushButton("Scan Bubble Sheets")
        self.scan_button.setFixedWidth(200)
        self.scan_button.setToolTip("Run the scanner to detect answers from the PNG images.")
        self.scan_button.clicked.connect(self._run_scanner)
        button_layout.addWidget(self.scan_button)

        self.review_results_button = QPushButton("Review Results")
        self.review_results_button.setFixedWidth(160)
        self.review_results_button.setEnabled(False)
        self.review_results_button.setToolTip("Open results.csv in your default viewer.")
        self.review_results_button.clicked.connect(self._review_results)
        button_layout.addWidget(self.review_results_button)

        self.review_log_button = QPushButton("Review Log")
        self.review_log_button.setFixedWidth(140)
        self.review_log_button.setEnabled(False)
        self.review_log_button.setToolTip("Open results.log with processing warnings.")
        self.review_log_button.clicked.connect(self._review_log)
        button_layout.addWidget(self.review_log_button)

        self.tips_button = QPushButton("Show Tips")
        self.tips_button.setFixedWidth(200)
        self.tips_button.setToolTip("Display scanning workflow tips and troubleshooting advice.")
        self.tips_button.clicked.connect(self._show_tips)
        button_layout.addWidget(self.tips_button)

        content_layout.addWidget(button_row, alignment=Qt.AlignmentFlag.AlignLeft)

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
        output_container.setMaximumWidth(900)

        self.output_view = QTextEdit()
        mono = QFont("Courier New", 11)
        self.output_view.setFont(mono)
        self.output_view.setReadOnly(True)
        self.output_view.setMinimumHeight(220)
        self.output_view.setToolTip("CLI output, status messages, or scanning tips appear here.")
        output_layout.addWidget(self.output_view)

        main_layout.addWidget(
            output_container,
            alignment=Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft,
        )

        main_layout.addStretch()

    def _default_images_dir(self) -> Path:
        active_folder = config.active_test_folder()
        if not active_folder:
            return config.TEST_BUILD_PATH
        return active_folder / "scanned_images"

    def _choose_custom_path(self) -> None:
        start_dir = str(self._default_images_dir())
        selected, _ = QFileDialog.getOpenFileName(
            self,
            "Select PNG or ZIP",
            start_dir,
            "PNG Files (*.png);;ZIP Files (*.zip);;All Files (*)",
        )
        if not selected:
            folder = QFileDialog.getExistingDirectory(self, "Select Folder Containing PNGs", start_dir)
            if folder:
                selected = folder
        if selected:
            self.custom_input.setText(selected)

    def _show_tips(self) -> None:
        self.output_view.clear()
        self.output_view.setPlainText(_TIPS_TEXT)

    def _collect_inputs(self) -> dict[str, object]:
        ready = self._evaluate_source_state(show_message=False)
        if not ready:
            raise ValueError("PNG inputs are not ready. Follow the guidance above.")

        assert self._source_path is not None
        assert self._layout_path is not None

        threshold_text = self.threshold_input.text().strip() or "0.5"
        try:
            threshold = float(threshold_text)
        except ValueError as exc:  # noqa: PERF203
            raise ValueError("Threshold must be a number between 0.0 and 1.0.") from exc
        if not 0.0 < threshold <= 1.0:
            raise ValueError("Threshold must be between 0.0 and 1.0.")

        active_folder = config.active_test_folder()
        assert active_folder is not None
        results_dir = active_folder / "results"
        results_dir.mkdir(parents=True, exist_ok=True)

        csv_path = results_dir / "results.csv"
        log_path = results_dir / "results.log"

        if self._source_path.is_file() and self._source_path.suffix.lower() == ".png":
            source_flag = "image"
        else:
            source_flag = "folder"

        return {
            "source_path": self._source_path,
            "source_flag": source_flag,
            "layout_path": self._layout_path,
            "threshold": threshold,
            "results_dir": results_dir,
            "csv_path": csv_path,
            "log_path": log_path,
            "log_enabled": self.log_checkbox.isChecked(),
        }

    def _run_scanner(self) -> None:
        try:
            params = self._collect_inputs()
        except ValueError as exc:
            QMessageBox.warning(self, "Check your inputs", str(exc))
            return

        command = self._build_command(params)
        self.scan_button.setEnabled(False)
        self.review_results_button.setEnabled(False)
        self.review_log_button.setEnabled(False)
        self.output_view.clear()
        self.output_view.append(f"$ {' '.join(shlex_quote(part) for part in command)}\n")

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
                "Scanner failed",
                "The CLI command reported an error. See the output panel for details.",
            )
        else:
            for chunk in (result.stdout.strip(), result.stderr.strip()):
                if chunk:
                    self.output_view.append(chunk + "\n")
            success = True
        finally:
            self.scan_button.setEnabled(True)
            self._refresh_existing_outputs()
            if not success and self._results_csv:
                self.review_results_button.setEnabled(True)
            if not success and self._results_log:
                self.review_log_button.setEnabled(True)

    def _build_command(self, params: dict[str, object]) -> list[str]:
        cmd = [
            str(config.PYTHON_EXECUTABLE),
            str(self._script_path),
            "--json",
            str(params["layout_path"]),
            "--output",
            "results.csv",
            "--output-dir",
            str(params["results_dir"]),
            "--threshold",
            str(params["threshold"]),
        ]
        if params["source_flag"] == "image":
            cmd.extend(["--image", str(params["source_path"])])
        else:
            cmd.extend(["--folder", str(params["source_path"])])

        if params["log_enabled"]:
            cmd.extend(["--log", "results.log"])
        return cmd

    def _review_results(self) -> None:
        self._refresh_existing_outputs()
        if not self._results_csv or not self._results_csv.exists():
            QMessageBox.information(
                self,
                "File not found",
                "Run the scanner first so there is a results.csv file to review.",
            )
            return
        self._open_path(self._results_csv)

    def _review_log(self) -> None:
        self._refresh_existing_outputs()
        if not self._results_log or not self._results_log.exists():
            QMessageBox.information(
                self,
                "File not found",
                "Enable log output and run the scanner to create results.log.",
            )
            return
        self._open_path(self._results_log)

    def _refresh_existing_outputs(self) -> None:
        active_folder = config.active_test_folder()
        if not active_folder:
            self._results_csv = None
            self._results_log = None
            self.review_results_button.setEnabled(False)
            self.review_log_button.setEnabled(False)
            return

        results_dir = active_folder / "results"
        csv_candidate = results_dir / "results.csv"
        log_candidate = results_dir / "results.log"

        if csv_candidate.exists():
            self._results_csv = csv_candidate
            self.review_results_button.setEnabled(True)
        else:
            self._results_csv = None
            self.review_results_button.setEnabled(False)

        if log_candidate.exists():
            self._results_log = log_candidate
            self.review_log_button.setEnabled(True)
        else:
            self._results_log = None
            self.review_log_button.setEnabled(False)

    def _open_path(self, path: Path) -> None:
        try:
            if sys.platform.startswith("win"):
                subprocess.Popen(["cmd", "/c", "start", "", str(path)])
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path)])
        except OSError as exc:  # noqa: PERF203
            QMessageBox.critical(self, "Viewer error", f"Could not open {path}: {exc}")

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._evaluate_source_state(show_message=True)
        self._refresh_existing_outputs()

    def _handle_custom_toggle(self) -> None:
        use_custom = self.custom_checkbox.isChecked()
        self.custom_input.setEnabled(use_custom)
        self.custom_browse.setEnabled(use_custom)
        self._evaluate_source_state(show_message=True)

    def _evaluate_source_state(self, show_message: bool) -> bool:
        active_folder = config.active_test_folder()
        exam_title = config.extract_exam_title()

        if not active_folder or not exam_title:
            self._source_path = None
            self._layout_path = None
            self.scan_button.setEnabled(False)
            self.default_path_display.setText("No test selected")
            if show_message:
                self._set_status_message("No test selected. Open the Test Manager tab and choose a test.", replace=True)
            return False

        default_path = self._default_images_dir()
        self.default_path_display.setText(str(default_path))
        layout_path = config.layout_json_path(active_folder, exam_title)
        if not layout_path or not layout_path.exists():
            self._source_path = None
            self._layout_path = None
            self.scan_button.setEnabled(False)
            if show_message:
                self._set_status_message("Layout JSON not found. Generate a bubble sheet before scanning.", replace=True)
            return False

        use_custom = self.custom_checkbox.isChecked()
        if use_custom:
            custom_text = self.custom_input.text().strip()
            if not custom_text:
                self._source_path = None
                self.scan_button.setEnabled(False)
                if show_message:
                    self._set_status_message("Enter a custom PNG path or uncheck 'Use custom PNGs'.", replace=True)
                return False
            source_path = Path(custom_text).expanduser()
        else:
            source_path = default_path

        valid, error = config.validate_scanner_inputs(source_path, layout_path)
        if valid:
            self._source_path = source_path
            self._layout_path = layout_path
            self.scan_button.setEnabled(True)
            if show_message and not self.output_view.toPlainText().strip():
                ready_message = f"PNGs found in {source_path}. Ready to scan."
                self._set_status_message(ready_message, replace=True)
            return True

        self._source_path = None
        self._layout_path = layout_path
        self.scan_button.setEnabled(False)
        message = error or "Invalid scanner inputs."
        if not use_custom and "PNG" in message:
            message = _MISSING_PNG_MESSAGE
        elif use_custom:
            message = f"{message}\n{_CUSTOM_WARNING}"
        if show_message:
            self._set_status_message(message, replace=True)
        return False

    def _set_status_message(self, message: str, *, replace: bool = False) -> None:
        if replace:
            self.output_view.setPlainText(message)
        else:
            self.output_view.append(message)


def shlex_quote(text: str) -> str:
    """Minimal shlex quoting to display commands in QTextEdit."""

    if not text:
        return "''"
    safe = "-._/:"
    if all(ch.isalnum() or ch in safe for ch in text):
        return text
    return "'" + text.replace("'", "'\"'\"'") + "'"
