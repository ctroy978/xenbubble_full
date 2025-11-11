"""QTI Test Generator tab for the Bubblexan Test Manager GUI."""

from __future__ import annotations

import re
import shlex
import subprocess
import sys
from pathlib import Path
from typing import TypedDict

import config
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QShowEvent
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
_XML_FILTER = "XML Files (*.xml);;All Files (*)"
_ZIP_FILTER = "ZIP Archives (*.zip);;All Files (*)"


class _FormValues(TypedDict):
    use_zip: bool
    zip_path: Path | None
    qti_path: Path | None
    meta_path: Path | None
    manifest_path: Path | None
    page_size: str
    output_prefix: str
    output_dir: Path
    pdf_path: Path
    csv_path: Path


class QtiTestGui(QWidget):
    """Tab that wraps bubblexan_cli/generate_test_from_qti.py."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        config.validate_cli_environment(["generate_test_from_qti.py"])
        self._script_path = config.CLI_PATH / "generate_test_from_qti.py"
        self._last_pdf: Path | None = None
        self._last_csv: Path | None = None
        self._init_ui()
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

        self.source_input = QLineEdit()
        self.source_input.setPlaceholderText("Path to Canvas QTI folder or ZIP")
        self.source_input.setToolTip("Select a folder or ZIP that contains a Canvas QTI export.")

        source_controls = QWidget()
        source_layout = QHBoxLayout(source_controls)
        source_layout.setContentsMargins(0, 0, 0, 0)
        source_layout.setSpacing(6)
        source_layout.addWidget(self.source_input)

        browse_folder_btn = QPushButton("Folder…")
        browse_folder_btn.setToolTip("Choose a folder that contains Canvas QTI files.")
        browse_folder_btn.clicked.connect(self._choose_folder)
        source_layout.addWidget(browse_folder_btn)

        browse_zip_btn = QPushButton("ZIP…")
        browse_zip_btn.setToolTip("Choose a Canvas QTI ZIP archive.")
        browse_zip_btn.clicked.connect(self._choose_zip)
        source_layout.addWidget(browse_zip_btn)

        form_layout.addRow("QTI Source:", source_controls)

        self.page_size_select = QComboBox()
        self.page_size_select.addItems(["A4", "LETTER"])
        self.page_size_select.setToolTip("Paper size for the generated test PDF.")
        form_layout.addRow("Page Size:", self.page_size_select)

        self.prefix_input = QLineEdit()
        self.prefix_input.setPlaceholderText("Defaults to the selected test name")
        self.prefix_input.setToolTip("Prefix for the output files (letters, numbers, underscores, hyphens).")
        form_layout.addRow("Output Prefix:", self.prefix_input)

        self.qti_override = self._build_override_field(
            "QTI XML Override:",
            "Choose a specific QTI XML file to use instead of auto-detecting one from the folder.",
        )
        form_layout.addRow("QTI XML Override:", self.qti_override["container"])

        self.meta_override = self._build_override_field(
            "Assessment Meta Override:",
            "Choose a custom assessment_meta.xml file.",
        )
        form_layout.addRow("assessment_meta.xml:", self.meta_override["container"])

        self.manifest_override = self._build_override_field(
            "IMS Manifest Override:",
            "Choose a custom imsmanifest.xml file.",
        )
        form_layout.addRow("imsmanifest.xml:", self.manifest_override["container"])

        content_layout.addLayout(form_layout)

        self.generate_button = QPushButton("Generate Test")
        self.generate_button.setFixedWidth(220)
        self.generate_button.setToolTip("Run the CLI tool to build the test PDF and answer key.")
        self.generate_button.clicked.connect(self._run_generator)
        content_layout.addWidget(self.generate_button, alignment=Qt.AlignmentFlag.AlignLeft)

        buttons_row = QWidget()
        buttons_layout = QHBoxLayout(buttons_row)
        buttons_layout.setContentsMargins(0, 0, 0, 0)
        buttons_layout.setSpacing(12)

        self.review_test_button = QPushButton("Review Test")
        self.review_test_button.setFixedWidth(160)
        self.review_test_button.setEnabled(False)
        self.review_test_button.setToolTip("Open the generated PDF in your default viewer.")
        self.review_test_button.clicked.connect(self._review_test)
        buttons_layout.addWidget(self.review_test_button)

        self.review_key_button = QPushButton("Review Answer Key")
        self.review_key_button.setFixedWidth(160)
        self.review_key_button.setEnabled(False)
        self.review_key_button.setToolTip("Open the generated answer key CSV.")
        self.review_key_button.clicked.connect(self._review_answer_key)
        buttons_layout.addWidget(self.review_key_button)

        content_layout.addWidget(buttons_row, alignment=Qt.AlignmentFlag.AlignLeft)

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
        self.output_view.setToolTip("CLI output and generated file paths.")
        output_layout.addWidget(self.output_view)

        main_layout.addWidget(
            output_container,
            alignment=Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft,
        )

        main_layout.addStretch()

    def _build_override_field(self, label_text: str, tooltip: str) -> dict[str, QWidget | QLineEdit]:
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        line_edit = QLineEdit()
        line_edit.setToolTip(tooltip)
        line_edit.setPlaceholderText(label_text.replace("Override:", "").strip())
        layout.addWidget(line_edit)

        browse_btn = QPushButton("Browse…")
        browse_btn.setToolTip(tooltip)
        browse_btn.clicked.connect(lambda: self._choose_file(line_edit, _XML_FILTER))
        layout.addWidget(browse_btn)

        return {"container": container, "input": line_edit}

    def _choose_folder(self) -> None:
        selected = QFileDialog.getExistingDirectory(self, "Select QTI Folder")
        if selected:
            self.source_input.setText(selected)

    def _choose_zip(self) -> None:
        selected, _ = QFileDialog.getOpenFileName(
            self,
            "Select QTI ZIP Archive",
            filter=_ZIP_FILTER,
        )
        if selected:
            self.source_input.setText(selected)

    def _choose_file(self, line_edit: QLineEdit, file_filter: str) -> None:
        selected, _ = QFileDialog.getOpenFileName(
            self,
            "Select File",
            filter=file_filter,
        )
        if selected:
            line_edit.setText(selected)

    def _open_file(self, path: Path | None, label: str) -> None:
        if not path or not path.exists():
            QMessageBox.information(
                self,
                "File not found",
                f"Generate a {label} first so there is a file to review.",
            )
            return

        try:
            if sys.platform.startswith("win"):
                subprocess.Popen(["cmd", "/c", "start", "", str(path)])
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path)])
        except OSError as exc:  # noqa: PERF203
            QMessageBox.critical(
                self,
                "Viewer error",
                f"Could not open the file: {exc}",
            )

    def _collect_inputs(self) -> _FormValues:
        active_folder = config.active_test_folder()
        if not active_folder:
            raise ValueError("No test selected. Please select a test in the Test Manager tab.")

        tests_dir = active_folder / "tests"
        tests_dir.mkdir(parents=True, exist_ok=True)

        source_text = self.source_input.text().strip()
        if not source_text:
            raise ValueError("Select a folder or ZIP with Canvas QTI files.")
        source_path = Path(source_text).expanduser()

        if not source_path.exists():
            raise ValueError("The selected QTI source does not exist.")

        is_zip = source_path.is_file() and source_path.suffix.lower() == ".zip"
        is_dir = source_path.is_dir()
        if not is_zip and not is_dir:
            raise ValueError("Select a folder or a .zip file that contains the QTI export.")

        missing = config.validate_qti_source(source_path)
        if missing:
            raise ValueError(
                "Cannot generate test. Missing files: " + ", ".join(missing)
            )

        prefix = self.prefix_input.text().strip() or (config.extract_exam_title() or "")
        if not prefix:
            raise ValueError("Output prefix cannot be empty. Enter one or select a test.")
        if not _PREFIX_PATTERN.fullmatch(prefix):
            raise ValueError("Output prefix must use letters, numbers, underscores, or hyphens.")
        self.prefix_input.setText(prefix)

        page_size = self.page_size_select.currentText().strip().upper()
        if page_size not in {"A4", "LETTER"}:
            raise ValueError("Page size must be A4 or LETTER.")

        override_qti = self._validate_override(self.qti_override["input"])
        override_meta = self._validate_override(self.meta_override["input"])
        override_manifest = self._validate_override(self.manifest_override["input"])

        if is_zip and any([override_qti, override_meta, override_manifest]):
            raise ValueError("Overrides are only supported when using a QTI folder, not a ZIP archive.")

        qti_path: Path | None = None
        meta_path: Path | None = None
        manifest_path: Path | None = None

        if is_zip:
            use_zip = True
            zip_path: Path | None = source_path
        else:
            use_zip = False
            zip_path = None
            folder = source_path
            qti_path = override_qti or config.find_primary_qti_xml(folder)
            if not qti_path:
                raise ValueError("Could not locate a primary QTI XML file in the selected folder.")
            meta_default, manifest_default = config.find_qti_support_files(folder)
            meta_path = override_meta or meta_default
            if not meta_path:
                raise ValueError("Could not locate assessment_meta.xml in the selected folder.")
            manifest_path = override_manifest or manifest_default
            if not manifest_path:
                raise ValueError("Could not locate imsmanifest.xml in the selected folder.")

        pdf_path = tests_dir / f"{prefix}_test.pdf"
        csv_path = tests_dir / f"{prefix}_answer_key.csv"

        return {
            "use_zip": use_zip,
            "zip_path": zip_path,
            "qti_path": qti_path,
            "meta_path": meta_path,
            "manifest_path": manifest_path,
            "page_size": page_size,
            "output_prefix": prefix,
            "output_dir": tests_dir,
            "pdf_path": pdf_path,
            "csv_path": csv_path,
        }

    def _validate_override(self, widget_obj: QWidget | QLineEdit) -> Path | None:
        if not isinstance(widget_obj, QLineEdit):
            return None
        text = widget_obj.text().strip()
        if not text:
            return None
        path = Path(text).expanduser()
        if not path.exists():
            raise ValueError(f"Override file '{path}' does not exist.")
        return path

    def _run_generator(self) -> None:
        try:
            params = self._collect_inputs()
        except ValueError as exc:
            QMessageBox.warning(self, "Check your inputs", str(exc))
            return

        command = self._build_command(params)
        self.generate_button.setEnabled(False)
        self.review_test_button.setEnabled(False)
        self.review_key_button.setEnabled(False)
        self.output_view.clear()
        self.output_view.append(f"$ {shlex.join(command)}\n")

        had_previous = self._last_pdf and self._last_pdf.exists() and self._last_csv and self._last_csv.exists()
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
            self._last_pdf = params["pdf_path"]
            self._last_csv = params["csv_path"]
            self.review_test_button.setEnabled(True)
            self.review_key_button.setEnabled(True)
            success = True
        finally:
            self.generate_button.setEnabled(True)
            if not success and had_previous:
                self.review_test_button.setEnabled(True)
                self.review_key_button.setEnabled(True)

    def _build_command(self, params: _FormValues) -> list[str]:
        cmd = [
            str(config.PYTHON_EXECUTABLE),
            str(self._script_path),
            "--output-dir",
            str(params["output_dir"]),
            "--output-prefix",
            params["output_prefix"],
            "--page-size",
            params["page_size"],
        ]
        if params["use_zip"]:
            cmd.extend(["--zip", str(params["zip_path"])])
        else:
            cmd.extend(
                [
                    "--qti",
                    str(params["qti_path"]),
                    "--meta",
                    str(params["meta_path"]),
                    "--manifest",
                    str(params["manifest_path"]),
                ]
            )
        return cmd

    def _format_summary(self, params: _FormValues) -> str:
        lines = [
            "Generated files:",
            str(params["pdf_path"]),
            str(params["csv_path"]),
        ]
        return "\n".join(lines)

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._refresh_existing_outputs()

    def _refresh_existing_outputs(self) -> None:
        active_folder = config.active_test_folder()
        title = config.extract_exam_title()
        if not active_folder or not title:
            self._last_pdf = None
            self._last_csv = None
            self.review_test_button.setEnabled(False)
            self.review_key_button.setEnabled(False)
            return

        tests_dir = active_folder / "tests"
        prefix = self.prefix_input.text().strip() or title
        if not self.prefix_input.text().strip():
            self.prefix_input.setText(prefix)

        pdf_candidate = tests_dir / f"{prefix}_test.pdf"
        csv_candidate = tests_dir / f"{prefix}_answer_key.csv"

        if pdf_candidate.exists():
            self._last_pdf = pdf_candidate
            self.review_test_button.setEnabled(True)
        else:
            self._last_pdf = None
            self.review_test_button.setEnabled(False)

        if csv_candidate.exists():
            self._last_csv = csv_candidate
            self.review_key_button.setEnabled(True)
        else:
            self._last_csv = None
            self.review_key_button.setEnabled(False)

    def _review_test(self) -> None:
        self._refresh_existing_outputs()
        self._open_file(self._last_pdf, "test PDF")

    def _review_answer_key(self) -> None:
        self._refresh_existing_outputs()
        self._open_file(self._last_csv, "answer key")
