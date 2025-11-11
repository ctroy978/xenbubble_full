"""Grading & Analysis tab for the Bubblexan Test Manager GUI."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from shlex import quote as shlex_quote

import config
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QDoubleValidator, QFont, QShowEvent
from PyQt6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

_GRADING_TIPS = """The Grading & Analysis tab generates student grades and highlights questions most students missed.

Workflow:
1. Run Bubble Sheet Scanner and ensure results.csv exists.
2. Ensure the answer key CSV exists (from QTI Test Generator or Answer Key Import).
3. Click "Generate Grades & Analysis" to run grading (always) and analysis (if enabled).
4. Review outputs with the buttons below.
5. Use the Grade Adjustment tab after reviewing miss rates to give back problematic questions.

Student Grades (grade.py):
- Inputs: results.csv (from Bubble Sheet Scanner) and <test_name>_answer_key.csv (from QTI/Answer Key Import).
- Scoring math:
  • Single-select: Full points if the answer matches exactly, otherwise 0.
  • Multi-select (point value P, C correct options): Each correct option = P/C points, each incorrect = -P/C. Raw score = (S_c − S_i) * (P / C), where S_c = correct selections, S_i = incorrect. Final score = max(0, raw score), rounded to 2 decimals.
  • Percent grade = (total_score / total_possible_points) * 100, rounded to 2 decimals.
  • Question percent_correct = (average score / max points) * 100.
- Outputs: grades/graded_report.csv, grades/graded_report.xlsx (Grades + Question_Stats sheets).

Question Analysis (analyze_misses.py):
- Inputs: Same results.csv and answer key.
- Highlights questions where more than the miss threshold percentage of students missed.
- Partial threshold controls how partial credit influences the miss calculation.
- Outputs: miss_analysis/miss_report.csv and optional miss_report.log.
"""


class GradingAnalysisGui(QWidget):
    """Tab integrating grade.py and analyze_misses.py."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        config.validate_cli_environment(["grade.py", "analyze_misses.py"])
        self._grade_script = config.CLI_PATH / "grade.py"
        self._misses_script = config.CLI_PATH / "analyze_misses.py"
        self._results_csv: Path | None = None
        self._answer_key_csv: Path | None = None
        self._grades_csv_path: Path | None = None
        self._grades_xlsx_path: Path | None = None
        self._miss_report_path: Path | None = None
        self._miss_log_path: Path | None = None
        self._init_ui()
        self._evaluate_inputs(show_message=True)
        self._refresh_existing_outputs()

    def _init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 10, 10, 10)

        form_container = QWidget(self)
        form_container.setMaximumWidth(620)
        form_layout = QFormLayout(form_container)
        form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        form_layout.setFormAlignment(Qt.AlignmentFlag.AlignTop)

        self.results_display = QLineEdit()
        self.results_display.setReadOnly(True)
        self.results_display.setToolTip("Results CSV from the Bubble Sheet Scanner tab.")
        form_layout.addRow("Results CSV:", self.results_display)

        self.answer_key_display = QLineEdit()
        self.answer_key_display.setReadOnly(True)
        self.answer_key_display.setToolTip("Answer key CSV generated from QTI Test Generator or Answer Key Import tab.")
        form_layout.addRow("Answer Key:", self.answer_key_display)

        self.analysis_checkbox = QCheckBox("Analyze Question Misses")
        self.analysis_checkbox.setChecked(True)
        self.analysis_checkbox.setToolTip("Generate miss_report.csv highlighting questions most students missed.")
        self.analysis_checkbox.stateChanged.connect(lambda _: self._toggle_analysis_controls())
        form_layout.addRow("", self.analysis_checkbox)

        self.miss_threshold_input = QLineEdit("50")
        self.miss_threshold_input.setValidator(QDoubleValidator(0.0, 100.0, 2, self))
        self.miss_threshold_input.setToolTip("Percentage of students missing a question to highlight (0-100%).")
        form_layout.addRow("Miss Threshold (%):", self.miss_threshold_input)

        self.partial_threshold_input = QLineEdit("1.0")
        self.partial_threshold_input.setValidator(QDoubleValidator(0.0, 1.0, 2, self))
        self.partial_threshold_input.setToolTip("Partial credit threshold for multi-select questions (0.0-1.0).")
        form_layout.addRow("Partial Threshold:", self.partial_threshold_input)

        self.analysis_log_checkbox = QCheckBox("Generate Analysis Log (miss_report.log)")
        form_layout.addRow("", self.analysis_log_checkbox)

        main_layout.addWidget(
            form_container,
            alignment=Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft,
        )

        button_row = QWidget()
        button_layout = QVBoxLayout(button_row)
        button_layout.setContentsMargins(0, 0, 0, 0)
        button_layout.setSpacing(8)

        self.generate_button = QPushButton("Generate Grades & Analysis")
        self.generate_button.setFixedWidth(260)
        self.generate_button.setToolTip("Run grade.py and analyze_misses.py using the detected inputs.")
        self.generate_button.clicked.connect(self._run_pipeline)
        button_layout.addWidget(self.generate_button, alignment=Qt.AlignmentFlag.AlignLeft)

        review_row = QWidget()
        review_layout = QVBoxLayout(review_row)
        review_layout.setContentsMargins(0, 0, 0, 0)
        review_layout.setSpacing(6)

        self.review_grades_csv_button = QPushButton("Review Grades CSV")
        self.review_grades_csv_button.setEnabled(False)
        self.review_grades_csv_button.setToolTip("Open grades/graded_report.csv.")
        self.review_grades_csv_button.clicked.connect(lambda: self._open_path(self._grades_csv_path, "student grades CSV"))
        review_layout.addWidget(self.review_grades_csv_button, alignment=Qt.AlignmentFlag.AlignLeft)

        self.review_grades_xlsx_button = QPushButton("Review Grades Excel")
        self.review_grades_xlsx_button.setEnabled(False)
        self.review_grades_xlsx_button.setToolTip("Open grades/graded_report.xlsx.")
        self.review_grades_xlsx_button.clicked.connect(lambda: self._open_path(self._grades_xlsx_path, "student grades Excel workbook"))
        review_layout.addWidget(self.review_grades_xlsx_button, alignment=Qt.AlignmentFlag.AlignLeft)

        self.review_miss_button = QPushButton("Review Miss Report")
        self.review_miss_button.setEnabled(False)
        self.review_miss_button.setToolTip("Open miss_analysis/miss_report.csv.")
        self.review_miss_button.clicked.connect(lambda: self._open_path(self._miss_report_path, "question miss report"))
        review_layout.addWidget(self.review_miss_button, alignment=Qt.AlignmentFlag.AlignLeft)

        self.review_miss_log_button = QPushButton("Review Miss Log")
        self.review_miss_log_button.setEnabled(False)
        self.review_miss_log_button.setToolTip("Open miss_analysis/miss_report.log.")
        self.review_miss_log_button.clicked.connect(lambda: self._open_path(self._miss_log_path, "question miss log"))
        review_layout.addWidget(self.review_miss_log_button, alignment=Qt.AlignmentFlag.AlignLeft)

        button_layout.addWidget(review_row)

        self.tips_button = QPushButton("Show Grading Tips")
        self.tips_button.setToolTip("Explain grading math and analysis workflow.")
        self.tips_button.clicked.connect(self._show_tips)
        button_layout.addWidget(self.tips_button, alignment=Qt.AlignmentFlag.AlignLeft)

        main_layout.addWidget(button_row, alignment=Qt.AlignmentFlag.AlignLeft)

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
        self.output_view.setMinimumHeight(230)
        self.output_view.setToolTip("Feedback from grading and analysis commands.")
        output_layout.addWidget(self.output_view)

        main_layout.addWidget(
            output_container,
            alignment=Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft,
        )

        main_layout.addStretch()
        self._toggle_analysis_controls()

    def _toggle_analysis_controls(self) -> None:
        enabled = self.analysis_checkbox.isChecked()
        self.miss_threshold_input.setEnabled(enabled)
        self.partial_threshold_input.setEnabled(enabled)
        self.analysis_log_checkbox.setEnabled(enabled)

    def _evaluate_inputs(self, show_message: bool) -> bool:
        active_folder = config.active_test_folder()
        exam_title = config.extract_exam_title()
        ok, error, results_path, key_path = config.grade_inputs_active(active_folder, exam_title)
        if ok:
            assert results_path and key_path
            self._results_csv = results_path
            self._answer_key_csv = key_path
            self.results_display.setText(str(results_path))
            self.answer_key_display.setText(str(key_path))
            self.generate_button.setEnabled(True)
            if show_message and not self.output_view.toPlainText():
                self.output_view.setPlainText("Inputs ready. Click “Generate Grades & Analysis” when you are ready.")
            return True

        self._results_csv = None
        self._answer_key_csv = None
        self.results_display.setText("Not found")
        self.answer_key_display.setText("Not found")
        self.generate_button.setEnabled(False)
        if show_message:
            self.output_view.setPlainText(error or "Missing inputs. Check the prior steps.")
        return False

    def _run_pipeline(self) -> None:
        if not self._evaluate_inputs(show_message=False):
            QMessageBox.warning(self, "Missing inputs", "Check that results.csv and the answer key are available.")
            return

        assert self._results_csv and self._answer_key_csv
        active_folder = config.active_test_folder()
        assert active_folder
        grades_dir = active_folder / "grades"
        grades_dir.mkdir(parents=True, exist_ok=True)
        miss_dir = active_folder / "miss_analysis"
        miss_dir.mkdir(parents=True, exist_ok=True)

        commands = []
        grade_cmd = [
            str(config.PYTHON_EXECUTABLE),
            str(self._grade_script),
            str(self._results_csv),
            str(self._answer_key_csv),
            "--output-dir",
            str(grades_dir),
        ]
        commands.append(("Student Grades", grade_cmd))

        if self.analysis_checkbox.isChecked():
            miss_cmd = [
                str(config.PYTHON_EXECUTABLE),
                str(self._misses_script),
                "--results",
                str(self._results_csv),
                "--key",
                str(self._answer_key_csv),
                "--output",
                str(miss_dir / "miss_report.csv"),
                "--miss-threshold",
                self.miss_threshold_input.text().strip() or "50",
                "--partial-threshold",
                self.partial_threshold_input.text().strip() or "1.0",
            ]
            if self.analysis_log_checkbox.isChecked():
                miss_cmd.extend(["--log", str(miss_dir / "miss_report.log")])
            commands.append(("Question Analysis", miss_cmd))

        self.generate_button.setEnabled(False)
        self.output_view.clear()
        success = True

        for title, command in commands:
            self.output_view.append(f"$ {' '.join(shlex_quote(part) for part in command)}\n")
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
                success = False
                break
            except subprocess.CalledProcessError as exc:  # noqa: PERF203
                self.output_view.append(exc.stdout)
                self.output_view.append(exc.stderr)
                QMessageBox.critical(
                    self,
                    f"{title} failed",
                    "The CLI command reported an error. See the output panel for details.",
                )
                success = False
                break
            else:
                if result.stdout.strip():
                    self.output_view.append(f"{title}:\n{result.stdout.strip()}\n")
                if result.stderr.strip():
                    self.output_view.append(result.stderr.strip() + "\n")

        self.generate_button.setEnabled(True)
        self._refresh_existing_outputs()

        if success:
            self.output_view.append("Done. Use the review buttons to open the generated files.")

    def _refresh_existing_outputs(self) -> None:
        active_folder = config.active_test_folder()
        if not active_folder:
            self._grades_csv_path = None
            self._grades_xlsx_path = None
            self._miss_report_path = None
            self._miss_log_path = None
            self._update_review_buttons()
            return

        grades_dir = active_folder / "grades"
        miss_dir = active_folder / "miss_analysis"
        self._grades_csv_path = grades_dir / "graded_report.csv"
        self._grades_xlsx_path = grades_dir / "graded_report.xlsx"
        self._miss_report_path = miss_dir / "miss_report.csv"
        self._miss_log_path = miss_dir / "miss_report.log"
        self._update_review_buttons()

    def _update_review_buttons(self) -> None:
        self.review_grades_csv_button.setEnabled(bool(self._grades_csv_path and self._grades_csv_path.exists()))
        self.review_grades_xlsx_button.setEnabled(bool(self._grades_xlsx_path and self._grades_xlsx_path.exists()))
        self.review_miss_button.setEnabled(bool(self._miss_report_path and self._miss_report_path.exists()))
        self.review_miss_log_button.setEnabled(bool(self.analysis_log_checkbox.isChecked() and self._miss_log_path and self._miss_log_path.exists()))

    def _open_path(self, path: Path | None, label: str) -> None:
        self._refresh_existing_outputs()
        if not path or not path.exists():
            QMessageBox.information(
                self,
                "File not found",
                f"Generate {label} first before reviewing.",
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
            QMessageBox.critical(self, "Viewer error", f"Could not open {path}: {exc}")

    def _show_tips(self) -> None:
        self.output_view.setPlainText(_GRADING_TIPS)

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._evaluate_inputs(show_message=False)
        self._refresh_existing_outputs()
