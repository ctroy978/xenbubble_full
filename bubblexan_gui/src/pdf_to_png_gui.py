"""UI for the PDF → PNG Converter tab."""

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
from PyQt6.QtGui import QIntValidator
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
    QComboBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from config import CLI_PATH, PROJECT_ROOT, PYTHON_EXECUTABLE, TEST_BUILD_PATH


class _FormValues(TypedDict):
    mode: str
    source_path: Path
    output_dir: Path
    dpi: int
    fmt: str
    prefix: str


class PdfToPngGui(QWidget):
    """Tab that wraps convert_pdf_to_png.py."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._script_path = CLI_PATH / "convert_pdf_to_png.py"
        self._review_target: Optional[Path] = None
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

        # Input type selection
        self.mode_group = QButtonGroup(self)
        input_mode_container = QWidget()
        mode_layout = QVBoxLayout(input_mode_container)
        mode_layout.setContentsMargins(0, 0, 0, 0)

        self.pdf_radio = QRadioButton("Single PDF file")
        self.folder_radio = QRadioButton("Folder of PDFs")
        self.zip_radio = QRadioButton("ZIP of PDFs")
        self.pdf_radio.setChecked(True)

        for btn in (self.pdf_radio, self.folder_radio, self.zip_radio):
            self.mode_group.addButton(btn)
            mode_layout.addWidget(btn)

        self.pdf_radio.setToolTip("Convert one PDF into individual page images.")
        self.folder_radio.setToolTip("Convert every PDF inside a folder (recursively).")
        self.zip_radio.setToolTip("Convert every PDF stored inside a .zip archive.")
        form_layout.addRow("Input Type:", input_mode_container)

        # Source path picker
        source_container = QWidget()
        source_layout = QVBoxLayout(source_container)
        source_layout.setContentsMargins(0, 0, 0, 0)
        source_layout.setSpacing(6)

        self.source_input = QLineEdit()
        self.source_input.setToolTip("Path to the PDF, folder, or .zip archive to convert.")
        source_layout.addWidget(self.source_input)

        source_browse = QPushButton("Browse…")
        source_browse.setToolTip("Choose the PDF, folder, or zip archive.")
        source_browse.clicked.connect(self._choose_source)
        source_layout.addWidget(source_browse, alignment=Qt.AlignmentFlag.AlignLeft)
        form_layout.addRow("Source Path:", source_container)

        self.output_dir_input = self._make_directory_row(
            form_layout,
            label="Output Folder:",
            tooltip="Folder where all images will be written.",
            default=str(PROJECT_ROOT / "output" / "png"),
        )

        dpi_container = QWidget()
        dpi_layout = QHBoxLayout(dpi_container)
        dpi_layout.setContentsMargins(0, 0, 0, 0)
        self.dpi_input = QLineEdit("300")
        self.dpi_input.setValidator(QIntValidator(72, 1200, self))
        self.dpi_input.setToolTip("Render resolution in DPI (higher = larger files).")
        dpi_layout.addWidget(self.dpi_input)
        form_layout.addRow("DPI:", dpi_container)

        self.format_select = QComboBox()
        self.format_select.addItems(["png", "jpg", "jpeg"])
        self.format_select.setCurrentText("png")
        self.format_select.setToolTip("Image format for the generated files.")
        form_layout.addRow("Format:", self.format_select)

        self.prefix_input = QLineEdit("exam1")
        self.prefix_input.setToolTip("Filename prefix, e.g., exam1_page01.png.")
        form_layout.addRow("Output Prefix:", self.prefix_input)

        content_layout.addLayout(form_layout)

        self.run_button = QPushButton("Convert to Images")
        self.run_button.setToolTip("Run the converter using the CLI tools.")
        self.run_button.setFixedWidth(220)
        self.run_button.clicked.connect(self._run_converter)
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

        self.review_button = QPushButton("Review Images")
        self.review_button.setToolTip("Open the output folder or the first generated image.")
        self.review_button.setFixedWidth(220)
        self.review_button.setEnabled(False)
        self.review_button.clicked.connect(self._open_review_target)
        main_layout.addWidget(
            self.review_button,
            alignment=Qt.AlignmentFlag.AlignLeft,
        )

        main_layout.addStretch()

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
        button.clicked.connect(lambda: self._choose_directory(line_edit))
        layout.addWidget(button, alignment=Qt.AlignmentFlag.AlignLeft)

        form_layout.addRow(label, container)
        return line_edit

    def _choose_source(self) -> None:
        start_path = self.source_input.text().strip() or str(TEST_BUILD_PATH)
        if self.folder_radio.isChecked():
            selected = QFileDialog.getExistingDirectory(
                self, "Select folder with PDFs", start_path
            )
        elif self.zip_radio.isChecked():
            selected, _ = QFileDialog.getOpenFileName(
                self,
                "Select ZIP archive",
                start_path,
                "Zip files (*.zip);;All files (*)",
            )
        else:
            selected, _ = QFileDialog.getOpenFileName(
                self,
                "Select PDF file",
                start_path,
                "PDF files (*.pdf);;All files (*)",
            )
        if selected:
            self.source_input.setText(selected)

    def _choose_directory(self, target: QLineEdit) -> None:
        start_dir = target.text().strip() or str(TEST_BUILD_PATH)
        selected = QFileDialog.getExistingDirectory(
            self, "Select output folder", start_dir
        )
        if selected:
            target.setText(selected)

    def _collect_inputs(self) -> _FormValues:
        mode = (
            "pdf"
            if self.pdf_radio.isChecked()
            else "folder"
            if self.folder_radio.isChecked()
            else "zip"
        )

        source_text = self.source_input.text().strip()
        if not source_text:
            raise ValueError("Please select a source PDF, folder, or ZIP.")
        source_path = Path(source_text).expanduser()

        if mode == "pdf":
            if not source_path.is_file() or source_path.suffix.lower() != ".pdf":
                raise ValueError("Selected source is not a PDF file.")
        elif mode == "folder":
            if not source_path.is_dir():
                raise ValueError("Selected source folder does not exist.")
        else:  # zip
            if not source_path.is_file() or source_path.suffix.lower() != ".zip":
                raise ValueError("Selected source is not a .zip archive.")

        output_dir = Path(self.output_dir_input.text()).expanduser()
        if not output_dir.is_absolute():
            output_dir = (PROJECT_ROOT / output_dir).resolve()
        output_dir.mkdir(parents=True, exist_ok=True)

        try:
            dpi = int(self.dpi_input.text())
        except ValueError:
            raise ValueError("DPI must be a whole number.") from None
        if dpi <= 0:
            raise ValueError("DPI must be greater than zero.")

        prefix = self.prefix_input.text().strip()
        if not prefix:
            raise ValueError("Output prefix cannot be empty.")

        return {
            "mode": mode,
            "source_path": source_path.resolve(),
            "output_dir": output_dir,
            "dpi": dpi,
            "fmt": self.format_select.currentText(),
            "prefix": prefix,
        }

    def _run_converter(self) -> None:
        try:
            params = self._collect_inputs()
        except ValueError as exc:
            QMessageBox.warning(self, "Check your input", str(exc))
            return

        command = self._build_command(params)
        self.run_button.setEnabled(False)
        self.review_button.setEnabled(False)
        self._review_target = None
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
                "Conversion failed",
                "The CLI command reported an error. See the output panel for details.",
            )
        else:
            messages = [result.stdout.strip(), result.stderr.strip()]
            for chunk in messages:
                if chunk:
                    self.output_view.append(chunk + "\n")
            summary = self._format_summary(params)
            self.output_view.append(summary)
            if self._review_target:
                self.review_button.setEnabled(True)
        finally:
            self.run_button.setEnabled(True)

    def _build_command(self, params: _FormValues) -> list[str]:
        cmd = [
            str(PYTHON_EXECUTABLE),
            str(self._script_path),
            "--output-dir",
            str(params["output_dir"]),
            "--dpi",
            str(params["dpi"]),
            "--fmt",
            params["fmt"],
            "--prefix",
            params["prefix"],
        ]

        if params["mode"] == "pdf":
            cmd.extend(["--pdf", str(params["source_path"])])
        else:
            cmd.extend(["--folder", str(params["source_path"])])
        return cmd

    def _format_summary(self, params: _FormValues) -> str:
        output_dir = params["output_dir"]
        pattern = f"{params['prefix']}_page*.{params['fmt']}"
        matches = sorted(output_dir.glob(pattern))

        if matches:
            self._review_target = matches[0]
        else:
            self._review_target = output_dir

        lines = [f"Images stored in: {output_dir}"]
        if matches:
            lines.append(f"Sample file: {matches[0]}")
        else:
            lines.append("No files detected yet; check converter logs.")
        return "\n".join(lines)

    def _open_review_target(self) -> None:
        if not self._review_target:
            QMessageBox.information(
                self,
                "No images",
                "Convert a PDF first, then try again.",
            )
            return

        target = self._review_target
        if not target.exists():
            QMessageBox.warning(
                self,
                "File missing",
                "The expected image could not be found. Re-run the converter.",
            )
            self.review_button.setEnabled(False)
            self._review_target = None
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
                "Could not open the output location with the default viewer.",
            )
