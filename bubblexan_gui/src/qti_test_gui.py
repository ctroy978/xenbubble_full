"""UI for the QTI Test Generator tab."""

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
from PyQt6.QtWidgets import (
    QFileDialog,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QComboBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from config import CLI_PATH, PROJECT_ROOT, PYTHON_EXECUTABLE, TEST_BUILD_PATH


class _FormValues(TypedDict):
    zip_path: Path
    qti_path: Optional[Path]
    meta_path: Optional[Path]
    manifest_path: Optional[Path]
    output_dir: Path
    output_prefix: str
    page_size: str


class QtiTestGui(QWidget):
    """Tab that wraps generate_test_from_qti.py."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._script_path = CLI_PATH / "generate_test_from_qti.py"
        self._latest_pdf: Optional[Path] = None
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

        self.zip_input = self._make_file_row(
            form_layout,
            label="Canvas ZIP:",
            tooltip="Select the Canvas QTI export (.zip).",
            button_text="Browse for ZIP…",
            dialog_caption="Select Canvas ZIP",
            filter_mask="Zip files (*.zip);;All files (*)",
        )

        self.qti_input = self._make_file_row(
            form_layout,
            label="QTI XML (optional):",
            tooltip="Override QTI XML path if you extracted it manually.",
            button_text="Browse for QTI XML…",
            dialog_caption="Select QTI XML",
            filter_mask="XML files (*.xml);;All files (*)",
        )

        self.meta_input = self._make_file_row(
            form_layout,
            label="Meta XML (optional):",
            tooltip="Optional assessment_meta.xml override.",
            button_text="Browse for meta XML…",
            dialog_caption="Select assessment_meta.xml",
            filter_mask="XML files (*.xml);;All files (*)",
        )

        self.manifest_input = self._make_file_row(
            form_layout,
            label="Manifest XML (optional):",
            tooltip="Optional imsmanifest.xml override.",
            button_text="Browse for manifest XML…",
            dialog_caption="Select imsmanifest.xml",
            filter_mask="XML files (*.xml);;All files (*)",
        )

        self.output_dir_input = self._make_file_row(
            form_layout,
            label="Output Folder:",
            tooltip="Folder where the generated PDF and answer key will be saved.",
            button_text="Browse for folder…",
            dialog_caption="Select Output Folder",
            is_directory=True,
            default_text=str(PROJECT_ROOT / "output"),
        )

        self.page_size_select = QComboBox()
        self.page_size_select.addItems(["A4", "LETTER"])
        self.page_size_select.setCurrentText("A4")
        self.page_size_select.setToolTip("Paper size for the generated PDF.")
        form_layout.addRow("Page Size:", self.page_size_select)

        self.output_prefix_input = QLineEdit("week2_exam")
        self.output_prefix_input.setToolTip("Prefix for the generated files (e.g., week2_exam).")
        form_layout.addRow("Output Prefix:", self.output_prefix_input)

        content_layout.addLayout(form_layout)

        self.run_button = QPushButton("Generate Test")
        self.run_button.setToolTip("Run the QTI Test Generator using the CLI tools.")
        self.run_button.setFixedWidth(220)
        self.run_button.clicked.connect(self._run_generator)
        content_layout.addWidget(
            self.run_button,
            alignment=Qt.AlignmentFlag.AlignLeft,
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

        self.review_button = QPushButton("Review / Print Test")
        self.review_button.setToolTip("Open the generated PDF in your default viewer.")
        self.review_button.setFixedWidth(220)
        self.review_button.setEnabled(False)
        self.review_button.clicked.connect(self._open_latest_pdf)
        main_layout.addWidget(
            self.review_button,
            alignment=Qt.AlignmentFlag.AlignLeft,
        )

        main_layout.addStretch()

    def _make_file_row(
        self,
        form_layout: QFormLayout,
        *,
        label: str,
        tooltip: str,
        button_text: str,
        dialog_caption: str,
        filter_mask: str = "All files (*)",
        is_directory: bool = False,
        default_text: str = "",
    ) -> QLineEdit:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        line_edit = QLineEdit(default_text)
        line_edit.setToolTip(tooltip)
        layout.addWidget(line_edit)

        button = QPushButton(button_text)
        button.setToolTip(tooltip)
        if is_directory:
            button.clicked.connect(lambda: self._choose_directory(line_edit, dialog_caption))
        else:
            button.clicked.connect(
                lambda: self._choose_file(line_edit, dialog_caption, filter_mask)
            )
        layout.addWidget(button, alignment=Qt.AlignmentFlag.AlignLeft)

        form_layout.addRow(label, container)
        return line_edit

    def _choose_directory(self, target: QLineEdit, caption: str) -> None:
        start_dir = target.text().strip() or str(TEST_BUILD_PATH)
        selected = QFileDialog.getExistingDirectory(self, caption, start_dir)
        if selected:
            target.setText(selected)

    def _choose_file(self, target: QLineEdit, caption: str, filter_mask: str) -> None:
        start_dir = target.text().strip() or str(TEST_BUILD_PATH)
        file_path, _ = QFileDialog.getOpenFileName(self, caption, start_dir, filter_mask)
        if file_path:
            target.setText(file_path)

    def _collect_inputs(self) -> _FormValues:
        def _ensure_file(path_str: str, label: str, required: bool) -> Optional[Path]:
            path_str = path_str.strip()
            if not path_str:
                if required:
                    raise ValueError(f"{label} is required.")
                return None
            candidate = Path(path_str).expanduser()
            if not candidate.is_file():
                raise ValueError(f"{label} was not found.")
            return candidate.resolve()

        zip_path = _ensure_file(self.zip_input.text(), "Canvas ZIP", True)
        qti_path = _ensure_file(self.qti_input.text(), "QTI XML", False)
        meta_path = _ensure_file(self.meta_input.text(), "Meta XML", False)
        manifest_path = _ensure_file(self.manifest_input.text(), "Manifest XML", False)

        output_prefix = self.output_prefix_input.text().strip()
        if not output_prefix:
            raise ValueError("Output prefix cannot be empty.")

        output_dir = Path(self.output_dir_input.text()).expanduser()
        if not output_dir.is_absolute():
            output_dir = (PROJECT_ROOT / output_dir).resolve()
        output_dir.mkdir(parents=True, exist_ok=True)

        return {
            "zip_path": zip_path,  # type: ignore[return-value]
            "qti_path": qti_path,
            "meta_path": meta_path,
            "manifest_path": manifest_path,
            "output_dir": output_dir,
            "output_prefix": output_prefix,
            "page_size": self.page_size_select.currentText(),
        }

    def _run_generator(self) -> None:
        try:
            params = self._collect_inputs()
        except ValueError as exc:
            QMessageBox.warning(self, "Check your input", str(exc))
            return

        command = self._build_command(params)
        self.run_button.setEnabled(False)
        self.review_button.setEnabled(False)
        self._latest_pdf = None
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
                "Test generator failed",
                "The CLI command reported an error. See the output panel for details.",
            )
        else:
            messages = [result.stdout.strip(), result.stderr.strip()]
            for chunk in messages:
                if chunk:
                    self.output_view.append(chunk + "\n")
            summary = self._format_summary(params)
            self.output_view.append(summary)
            if self._latest_pdf:
                self.review_button.setEnabled(True)
        finally:
            self.run_button.setEnabled(True)

    def _build_command(self, params: _FormValues) -> list[str]:
        cmd = [
            str(PYTHON_EXECUTABLE),
            str(self._script_path),
            "--zip",
            str(params["zip_path"]),
            "--output-dir",
            str(params["output_dir"]),
            "--output-prefix",
            params["output_prefix"],
            "--page-size",
            params["page_size"],
        ]

        if params["qti_path"]:
            cmd.extend(["--qti", str(params["qti_path"])])
        if params["meta_path"]:
            cmd.extend(["--meta", str(params["meta_path"])])
        if params["manifest_path"]:
            cmd.extend(["--manifest", str(params["manifest_path"])])

        return cmd

    def _format_summary(self, params: _FormValues) -> str:
        prefix = params["output_prefix"]
        pdf = params["output_dir"] / f"{prefix}_test.pdf"
        csv = params["output_dir"] / f"{prefix}_answer_key.csv"
        self._latest_pdf = pdf if pdf.exists() else None

        lines = ["Generated files:"]
        lines.append(str(pdf))
        lines.append(str(csv))
        if not pdf.exists():
            lines.append("PDF not found yet. Review button stays disabled.")
        return "\n".join(lines)

    def _open_latest_pdf(self) -> None:
        if not self._latest_pdf:
            QMessageBox.information(
                self,
                "No PDF",
                "Generate a test first, then try again.",
            )
            return

        pdf_path = self._latest_pdf
        if not pdf_path.exists():
            QMessageBox.warning(
                self,
                "File missing",
                "The generated PDF could not be found. Re-run the generator.",
            )
            self.review_button.setEnabled(False)
            self._latest_pdf = None
            return

        try:
            if sys.platform == "win32":
                subprocess.run(["cmd", "/c", "start", "", str(pdf_path)], check=True)
            elif sys.platform == "darwin":
                subprocess.run(["open", str(pdf_path)], check=True)
            else:
                subprocess.run(["xdg-open", str(pdf_path)], check=True)
        except subprocess.CalledProcessError:
            QMessageBox.critical(
                self,
                "Open failed",
                "Could not open the PDF with the default viewer.",
            )
