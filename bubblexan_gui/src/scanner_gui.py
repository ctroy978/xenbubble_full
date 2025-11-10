"""UI for the Bubble Sheet Scanner tab."""

from __future__ import annotations

import shlex
import subprocess
import sys
from pathlib import Path
from typing import Optional, TypedDict

SRC_DIR = Path(__file__).resolve().parent
GUI_ROOT = SRC_DIR.parent
if str(GUI_ROOT) not in sys.path:
    sys.path.insert(0, str(GUI_ROOT))

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QDoubleValidator
from PyQt6.QtWidgets import (
    QButtonGroup,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QCheckBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from config import CLI_PATH, PROJECT_ROOT, PYTHON_EXECUTABLE


class _FormValues(TypedDict):
    mode: str
    source_path: Path
    layout_json: Path
    output_csv: Path
    output_dir: Path
    threshold: float
    log_enabled: bool
    log_path: Optional[Path]


class ScannerGui(QWidget):
    """Tab that wraps scan_bubblesheet.py."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._script_path = CLI_PATH / "scan_bubblesheet.py"
        self._latest_csv: Optional[Path] = None
        self._init_ui()

    def _init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 10, 10, 10)

        content_widget = QWidget(self)
        content_widget.setMaximumWidth(900)
        content_layout = QHBoxLayout(content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(24)

        left_form = QFormLayout()
        left_form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        left_form.setFormAlignment(Qt.AlignmentFlag.AlignTop)

        right_form = QFormLayout()
        right_form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        right_form.setFormAlignment(Qt.AlignmentFlag.AlignTop)

        self.mode_group = QButtonGroup(self)
        mode_container = QWidget()
        mode_layout = QVBoxLayout(mode_container)
        mode_layout.setContentsMargins(0, 0, 0, 0)

        self.image_radio = QRadioButton("Single image file")
        self.folder_radio = QRadioButton("Folder of scans")
        self.zip_radio = QRadioButton("ZIP archive")
        self.image_radio.setChecked(True)
        for btn in (self.image_radio, self.folder_radio, self.zip_radio):
            self.mode_group.addButton(btn)
            mode_layout.addWidget(btn)

        self.image_radio.setToolTip("Process one image file (PNG/JPG).")
        self.folder_radio.setToolTip("Process every image in a folder (or nested folders).")
        self.zip_radio.setToolTip("Process images contained inside a .zip archive.")
        left_form.addRow("Input Type:", mode_container)

        self.source_input = self._make_path_row(
            left_form,
            label="Source Path:",
            tooltip="Path to the scanned image, folder, or .zip archive.",
            button_text="Browse…",
            file_filters={
                "image": "Images (*.png *.jpg *.jpeg);;All files (*)",
                "folder": None,
                "zip": "Zip files (*.zip);;All files (*)",
            },
        )

        self.layout_input = self._make_path_row(
            left_form,
            label="Layout JSON:",
            tooltip="JSON file produced by the Bubble Sheet Generator.",
            button_text="Browse for JSON…",
            file_filters={"default": "JSON files (*.json);;All files (*)"},
        )

        self.output_csv_input = self._make_path_row(
            right_form,
            label="Output CSV:",
            tooltip="Where the scanner should save results (e.g., results.csv).",
            button_text="Select CSV…",
            default=str(PROJECT_ROOT / "output" / "results.csv"),
            file_filters={"default": "CSV files (*.csv);;All files (*)"},
        )

        self.threshold_input = QLineEdit("0.5")
        validator = QDoubleValidator(0.0, 1.0, 2, self)
        validator.setNotation(QDoubleValidator.Notation.StandardNotation)
        self.threshold_input.setValidator(validator)
        self.threshold_input.setToolTip("Bubble fill detection threshold (0-1).")
        right_form.addRow("Threshold:", self.threshold_input)

        self.output_dir_input = self._make_path_row(
            right_form,
            label="Output Folder:",
            tooltip="Folder for CSV and optional log file.",
            button_text="Browse for folder…",
            default=str(PROJECT_ROOT / "output"),
            directory_only=True,
        )

        self.log_checkbox = QCheckBox("Save log file")
        self.log_checkbox.setToolTip("Enable to write a log alongside the CSV.")
        self.log_checkbox.toggled.connect(self._toggle_log_inputs)
        log_container = QWidget()
        log_layout = QVBoxLayout(log_container)
        log_layout.setContentsMargins(0, 0, 0, 0)
        log_layout.setSpacing(6)
        self.log_path_input = QLineEdit(str(PROJECT_ROOT / "output" / "results.log"))
        self.log_path_input.setEnabled(False)
        self.log_path_input.setToolTip("Path to the log file if logging is enabled.")
        log_layout.addWidget(self.log_checkbox)
        log_layout.addWidget(self.log_path_input)

        log_browse = QPushButton("Browse for log…")
        log_browse.setEnabled(False)
        log_browse.setToolTip("Choose a custom log file path.")
        log_browse.clicked.connect(lambda: self._choose_log_file(log_browse))
        self._log_browse_button = log_browse
        log_layout.addWidget(log_browse, alignment=Qt.AlignmentFlag.AlignLeft)

        right_form.addRow("Logging:", log_container)

        content_layout.addLayout(left_form)
        content_layout.addLayout(right_form)

        self.run_button = QPushButton("Scan Bubble Sheets")
        self.run_button.setToolTip("Run the scanner using the CLI tools.")
        self.run_button.setFixedWidth(220)
        self.run_button.clicked.connect(self._run_scanner)
        content_layout.addWidget(self.run_button, alignment=Qt.AlignmentFlag.AlignLeft)

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

        self.review_button = QPushButton("Review Results")
        self.review_button.setToolTip("Open the results CSV in your default spreadsheet app.")
        self.review_button.setFixedWidth(220)
        self.review_button.setEnabled(False)
        self.review_button.clicked.connect(self._open_latest_csv)
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
        file_filters: dict[str, Optional[str]] | None = None,
        directory_only: bool = False,
    ) -> QLineEdit:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        line_edit = QLineEdit(default)
        line_edit.setToolTip(tooltip)
        layout.addWidget(line_edit)

        button = QPushButton(button_text)
        button.setToolTip(tooltip)

        def _on_click() -> None:
            start_dir = line_edit.text().strip() or str(PROJECT_ROOT)
            if directory_only:
                selected = QFileDialog.getExistingDirectory(
                    self, "Select folder", start_dir
                )
                if selected:
                    line_edit.setText(selected)
                return

            # Determine filter
            filter_text = None
            if file_filters:
                if self.image_radio.isChecked():
                    filter_text = file_filters.get("image") or file_filters.get("default")
                elif self.folder_radio.isChecked():
                    filter_text = file_filters.get("folder") or file_filters.get("default")
                elif self.zip_radio.isChecked():
                    filter_text = file_filters.get("zip") or file_filters.get("default")
                else:
                    filter_text = file_filters.get("default")
            selected, _ = QFileDialog.getOpenFileName(
                self,
                "Select file",
                start_dir,
                filter_text or "All files (*)",
            )
            if selected:
                line_edit.setText(selected)

        button.clicked.connect(_on_click)
        layout.addWidget(button, alignment=Qt.AlignmentFlag.AlignLeft)

        form_layout.addRow(label, container)
        return line_edit

    def _toggle_log_inputs(self, checked: bool) -> None:
        self.log_path_input.setEnabled(checked)
        self._log_browse_button.setEnabled(checked)

    def _choose_log_file(self, button: QPushButton) -> None:
        start_path = self.log_path_input.text().strip() or str(PROJECT_ROOT)
        selected, _ = QFileDialog.getSaveFileName(
            self,
            "Select log file",
            start_path,
            "Log files (*.log);;All files (*)",
        )
        if selected:
            self.log_path_input.setText(selected)

    def _collect_inputs(self) -> _FormValues:
        mode = (
            "image"
            if self.image_radio.isChecked()
            else "folder"
            if self.folder_radio.isChecked()
            else "zip"
        )

        source_path = Path(self.source_input.text().strip()).expanduser()
        if not source_path.exists():
            raise ValueError("Source path does not exist.")
        if mode == "image" and not source_path.is_file():
            raise ValueError("Selected source must be a single image file.")
        if mode == "folder" and not source_path.is_dir():
            raise ValueError("Selected folder does not exist.")
        if mode == "zip" and not (source_path.is_file() and source_path.suffix.lower() == ".zip"):
            raise ValueError("Selected source must be a .zip archive.")

        layout_json = Path(self.layout_input.text().strip()).expanduser()
        if not (layout_json.is_file() and layout_json.suffix.lower() == ".json"):
            raise ValueError("Layout JSON file is required.")

        output_csv = Path(self.output_csv_input.text().strip()).expanduser()
        if output_csv.is_dir():
            raise ValueError("Output CSV must be a file path.")
        output_csv.parent.mkdir(parents=True, exist_ok=True)

        output_dir = Path(self.output_dir_input.text().strip()).expanduser()
        if not output_dir.is_absolute():
            output_dir = (PROJECT_ROOT / output_dir).resolve()
        output_dir.mkdir(parents=True, exist_ok=True)

        try:
            threshold = float(self.threshold_input.text())
        except ValueError:
            raise ValueError("Threshold must be a number between 0 and 1.") from None
        if not (0.0 <= threshold <= 1.0):
            raise ValueError("Threshold must be between 0 and 1.")

        log_enabled = self.log_checkbox.isChecked()
        log_path = None
        if log_enabled:
            log_path = Path(self.log_path_input.text().strip()).expanduser()
            if not log_path:
                raise ValueError("Specify a log file path or disable logging.")
            log_path.parent.mkdir(parents=True, exist_ok=True)

        return {
            "mode": mode,
            "source_path": source_path.resolve(),
            "layout_json": layout_json.resolve(),
            "output_csv": output_csv.resolve(),
            "output_dir": output_dir,
            "threshold": threshold,
            "log_enabled": log_enabled,
            "log_path": log_path.resolve() if log_path else None,
        }

    def _run_scanner(self) -> None:
        try:
            params = self._collect_inputs()
        except ValueError as exc:
            QMessageBox.warning(self, "Check your input", str(exc))
            return

        command = self._build_command(params)
        self.run_button.setEnabled(False)
        self.review_button.setEnabled(False)
        self._latest_csv = None
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
                "Scanner failed",
                "The CLI command reported an error. See the output panel for details.",
            )
        else:
            messages = [result.stdout.strip(), result.stderr.strip()]
            for chunk in messages:
                if chunk:
                    self.output_view.append(chunk + "\n")
            summary = self._format_summary(params)
            self.output_view.append(summary)
            if self._latest_csv and self._latest_csv.exists():
                self.review_button.setEnabled(True)
        finally:
            self.run_button.setEnabled(True)

    def _build_command(self, params: _FormValues) -> list[str]:
        cmd = [
            str(PYTHON_EXECUTABLE),
            str(self._script_path),
            "--json",
            str(params["layout_json"]),
            "--output",
            str(params["output_csv"]),
            "--output-dir",
            str(params["output_dir"]),
            "--threshold",
            str(params["threshold"]),
        ]

        if params["mode"] == "image":
            cmd.extend(["--image", str(params["source_path"])])
        else:
            cmd.extend(["--folder", str(params["source_path"])])

        if params["log_enabled"] and params["log_path"]:
            cmd.extend(["--log", str(params["log_path"])])

        return cmd

    def _format_summary(self, params: _FormValues) -> str:
        self._latest_csv = params["output_csv"]
        lines = ["Results stored at:", str(self._latest_csv)]
        if params["log_enabled"] and params["log_path"]:
            lines.append(f"Log file: {params['log_path']}")
        return "\n".join(lines)

    def _open_latest_csv(self) -> None:
        if not self._latest_csv:
            QMessageBox.information(
                self,
                "No results yet",
                "Run the scanner first, then review the CSV.",
            )
            return

        target = self._latest_csv
        if not target.exists():
            QMessageBox.warning(
                self,
                "File missing",
                "The results CSV could not be found. Re-run the scanner.",
            )
            self.review_button.setEnabled(False)
            self._latest_csv = None
            return

        path_to_open = str(target)
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
                "Could not open the CSV with the default viewer.",
            )
