"""PDF to PNG Conversion tab for the Bubblexan Test Manager GUI."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import config
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QIntValidator
from PyQt6.QtWidgets import (
    QComboBox,
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

_PREFIX_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")
_TIPS_TEXT = """The PDF to PNG Conversion tab converts scanned bubble sheet PDFs into PNG images for processing by the Bubble Sheet Scanner.

Workflow:
1. Scan bubble sheets as one multi-page PDF (one page per student, 300 DPI, grayscale) using your scanner’s ADF.
2. Save the PDF to inputs/scans/ for your test or select it here.
3. Click "Convert to Images" to generate PNGs in scanned_images/ (e.g., exam1_page01.png).
4. Use the Bubble Sheet Scanner tab to process the PNGs.

Tips:
- Use 300 DPI and grayscale for optimal bubble detection.
- Ensure borders and alignment markers are fully visible.
- Ask students to use #2 pencils and fully darken bubbles.
- Avoid staples, tape, or lamination.
- Large PDFs may take several minutes to convert.
"""


class PdfToPngGui(QWidget):
    """Tab that wraps bubblexan_cli/convert_pdf_to_png.py."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        config.validate_cli_environment(["convert_pdf_to_png.py"])
        self._script_path = config.CLI_PATH / "convert_pdf_to_png.py"
        self._last_output_dir: Path | None = None
        self._last_first_image: Path | None = None
        self._init_ui()

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

        self.source_input = QLineEdit()
        self.source_input.setPlaceholderText("Select a PDF, folder, or ZIP")
        self.source_input.setToolTip("Select a PDF, folder, or ZIP of scanned bubble sheets.")
        source_controls = QWidget()
        source_layout = QHBoxLayout(source_controls)
        source_layout.setContentsMargins(0, 0, 0, 0)
        source_layout.setSpacing(6)
        source_layout.addWidget(self.source_input)

        file_button = QPushButton("File…")
        file_button.setToolTip("Choose a single PDF or ZIP file.")
        file_button.clicked.connect(self._choose_file)
        source_layout.addWidget(file_button)

        folder_button = QPushButton("Folder…")
        folder_button.setToolTip("Choose a folder that contains PDFs.")
        folder_button.clicked.connect(self._choose_folder)
        source_layout.addWidget(folder_button)

        form_layout.addRow("Input Source:", source_controls)

        self.dpi_input = QLineEdit("300")
        self.dpi_input.setValidator(QIntValidator(100, 600, self))
        self.dpi_input.setToolTip("Resolution in dots per inch (100–600). 300 DPI is recommended.")
        form_layout.addRow("DPI:", self.dpi_input)

        self.format_select = QComboBox()
        self.format_select.addItems(["PNG", "JPG"])
        self.format_select.setToolTip("Output image format (PNG recommended).")
        form_layout.addRow("Image Format:", self.format_select)

        prefix_default = config.extract_exam_title() or ""
        self.prefix_input = QLineEdit(prefix_default)
        self.prefix_input.setPlaceholderText("exam1")
        self.prefix_input.setToolTip("Prefix for output filenames (letters, numbers, underscores, hyphens).")
        form_layout.addRow("Filename Prefix:", self.prefix_input)

        content_layout.addLayout(form_layout)

        button_row = QWidget()
        button_layout = QHBoxLayout(button_row)
        button_layout.setContentsMargins(0, 0, 0, 0)
        button_layout.setSpacing(12)

        self.convert_button = QPushButton("Convert to Images")
        self.convert_button.setFixedWidth(200)
        self.convert_button.setToolTip("Run the CLI tool to convert PDFs into PNGs.")
        self.convert_button.clicked.connect(self._run_converter)
        button_layout.addWidget(self.convert_button)

        self.review_button = QPushButton("Review Images")
        self.review_button.setFixedWidth(160)
        self.review_button.setEnabled(False)
        self.review_button.setToolTip("Open the output folder to inspect the generated images.")
        self.review_button.clicked.connect(self._review_images)
        button_layout.addWidget(self.review_button)

        self.tips_button = QPushButton("Show Conversion Tips")
        self.tips_button.setFixedWidth(200)
        self.tips_button.setToolTip("Display scanning and conversion guidance.")
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
        self.output_view.setToolTip("CLI output and conversion tips appear here.")
        output_layout.addWidget(self.output_view)

        main_layout.addWidget(
            output_container,
            alignment=Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft,
        )

        main_layout.addStretch()

    def _default_scans_dir(self) -> Path:
        active_folder = config.active_test_folder()
        if not active_folder:
            return config.TEST_BUILD_PATH
        return active_folder / "inputs" / "scans"

    def _choose_file(self) -> None:
        start_dir = str(self._default_scans_dir())
        selected, _ = QFileDialog.getOpenFileName(
            self,
            "Select PDF or ZIP",
            start_dir,
            "PDF Files (*.pdf);;ZIP Files (*.zip);;All Files (*)",
        )
        if selected:
            self.source_input.setText(selected)

    def _choose_folder(self) -> None:
        start_dir = str(self._default_scans_dir())
        selected = QFileDialog.getExistingDirectory(self, "Select Folder Containing PDFs", start_dir)
        if selected:
            self.source_input.setText(selected)

    def _show_tips(self) -> None:
        self.output_view.clear()
        self.output_view.setPlainText(_TIPS_TEXT)

    def _collect_inputs(self) -> dict[str, object]:
        active_folder = config.active_test_folder()
        if not active_folder:
            raise ValueError("No test selected. Please select a test in the Test Manager tab.")

        source_text = self.source_input.text().strip()
        if not source_text:
            raise ValueError("Select a PDF file, folder, or ZIP archive to convert.")
        source_path = Path(source_text).expanduser()

        errors = config.validate_pdf_input(source_path)
        if errors:
            raise ValueError(", ".join(errors))

        dpi_text = self.dpi_input.text().strip()
        if not dpi_text:
            raise ValueError("DPI value cannot be empty.")
        try:
            dpi = int(dpi_text)
        except ValueError as exc:  # noqa: PERF203
            raise ValueError("DPI must be a number between 100 and 600.") from exc
        if not 100 <= dpi <= 600:
            raise ValueError("DPI must be between 100 and 600.")

        prefix = self.prefix_input.text().strip() or (config.extract_exam_title() or "")
        if not prefix:
            raise ValueError("Filename prefix cannot be empty. Enter one or select a test.")
        if not _PREFIX_PATTERN.fullmatch(prefix):
            raise ValueError("Prefix must use letters, numbers, underscores, or hyphens.")
        self.prefix_input.setText(prefix)

        fmt_selection = self.format_select.currentText().strip().lower()
        fmt = "jpg" if fmt_selection == "jpg" else "png"

        if not config.poppler_available():
            raise RuntimeError(
                "Poppler (pdftoppm) is required. Install via 'apt install poppler-utils' (Ubuntu), "
                "'brew install poppler' (macOS), or download from poppler.freedesktop.org."
            )

        output_dir = active_folder / "scanned_images"
        output_dir.mkdir(parents=True, exist_ok=True)

        if source_path.is_file() and source_path.suffix.lower() == ".pdf":
            source_flag = "pdf"
        else:
            source_flag = "folder"

        first_image = output_dir / f"{prefix}_page01.{fmt}"

        return {
            "source_path": source_path,
            "source_flag": source_flag,
            "dpi": dpi,
            "fmt": fmt,
            "prefix": prefix,
            "output_dir": output_dir,
            "first_image": first_image,
        }

    def _run_converter(self) -> None:
        try:
            params = self._collect_inputs()
        except ValueError as exc:
            QMessageBox.warning(self, "Check your inputs", str(exc))
            return
        except RuntimeError as exc:
            QMessageBox.critical(self, "Missing dependency", str(exc))
            return

        command = self._build_command(params)
        self.convert_button.setEnabled(False)
        self.review_button.setEnabled(False)
        self.output_view.clear()
        self.output_view.append(f"$ {' '.join(shlex_quote(part) for part in command)}\n")

        success = False
        had_previous = self._last_output_dir is not None
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
                "Conversion failed",
                "The CLI command reported an error. See the output panel for details.",
            )
        else:
            for chunk in (result.stdout.strip(), result.stderr.strip()):
                if chunk:
                    self.output_view.append(chunk + "\n")
            self.output_view.append(
                f"Images saved to {params['output_dir']}\nFirst image: {params['first_image']}"
            )
            self._last_output_dir = params["output_dir"]
            self._last_first_image = params["first_image"]
            self.review_button.setEnabled(True)
            success = True
        finally:
            self.convert_button.setEnabled(True)
            if not success and had_previous and self._last_output_dir:
                self.review_button.setEnabled(True)

    def _build_command(self, params: dict[str, object]) -> list[str]:
        cmd = [
            str(config.PYTHON_EXECUTABLE),
            str(self._script_path),
            "--output-dir",
            str(params["output_dir"]),
            "--dpi",
            str(params["dpi"]),
            "--fmt",
            str(params["fmt"]),
            "--prefix",
            str(params["prefix"]),
        ]
        if params["source_flag"] == "pdf":
            cmd.extend(["--pdf", str(params["source_path"])])
        else:
            cmd.extend(["--folder", str(params["source_path"])])
        return cmd

    def _review_images(self) -> None:
        target = self._last_output_dir
        if not target or not target.exists():
            QMessageBox.information(
                self,
                "Folder not found",
                "Run a successful conversion first so there are images to review.",
            )
            return

        try:
            self._open_path(target)
        except OSError:
            if self._last_first_image and self._last_first_image.exists():
                try:
                    self._open_path(self._last_first_image)
                    return
                except OSError as exc:  # noqa: PERF203
                    QMessageBox.critical(self, "Viewer error", f"Could not open images: {exc}")
            else:
                QMessageBox.critical(
                    self,
                    "Viewer error",
                    "Could not open the output folder or any image file.",
                )

    def _open_path(self, path: Path) -> None:
        if sys.platform.startswith("win"):
            subprocess.Popen(["explorer", str(path)])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])


def shlex_quote(text: str) -> str:
    """Minimal shlex quoting to display commands in QTextEdit."""

    if not text:
        return "''"
    if all(ch.isalnum() or ch in "-._/:" for ch in text):
        return text
    return "'" + text.replace("'", "'\"'\"'") + "'"
