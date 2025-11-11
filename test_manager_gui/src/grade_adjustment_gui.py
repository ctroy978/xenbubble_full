"""Grade Adjustment tab for giving back questions."""

from __future__ import annotations

import csv
import subprocess
import sys
import tempfile
from pathlib import Path
from shlex import quote as shlex_quote

import config
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QShowEvent
from PyQt6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QComboBox,
)

_ADJUSTMENT_TIPS = """The Grade Adjustment tab lets you "give back" selected questions so every student receives full credit for them, without touching the original results.

Workflow:
1. Review miss_report.csv in the Grading & Analysis tab to identify problematic questions (e.g., >50% missed).
2. Select those questions here (or type them manually), then preview to see the impact.
3. Save each adjustment under a unique version name (e.g., adjustment_1). All files are stored in adjustments/.
4. Use the dropdown to review previous versions. When satisfied, click Finalize Grades to copy that version into grades/.

Scoring math during re-grading:
- Single-select questions: Full points if the recorded answer matches the key (or the question is given back); otherwise 0.
- Multi-select questions (point value P, C correct options):
  • Each correct option = P/C points.
  • Each incorrect option = -P/C points.
  • Raw score = (S_c − S_i) * (P / C), where S_c = correct selections and S_i = incorrect selections.
  • Final score = max(0, raw score), rounded to two decimals.
- Percent grade = (total_score / total_possible_points) * 100, rounded to two decimals.
- Given-back questions award all students the full point value automatically.
"""


class GradeAdjustmentGui(QWidget):
    """Tab that wraps give_back_questions.py with version management."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        config.validate_cli_environment(["give_back_questions.py", "grade.py"])
        self._script_path = config.CLI_PATH / "give_back_questions.py"
        self._results_path: Path | None = None
        self._answer_key_path: Path | None = None
        self._miss_report_path: Path | None = None
        self._available_questions: list[dict[str, str]] = []
        self._versions: list[str] = []
        self._init_ui()
        self._evaluate_inputs(show_message=True)
        self._refresh_versions()

    def _init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 10, 10, 10)

        form_container = QWidget(self)
        form_container.setMaximumWidth(720)
        form_layout = QFormLayout(form_container)
        form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        form_layout.setFormAlignment(Qt.AlignmentFlag.AlignTop)

        self.results_display = self._make_path_display("Results CSV:", form_layout, "results/results.csv")
        self.answer_key_display = self._make_path_display("Answer Key:", form_layout, "tests/<test>_answer_key.csv")
        self.miss_report_display = self._make_path_display("Miss Report:", form_layout, "miss_analysis/miss_report.csv")

        main_layout.addWidget(form_container, alignment=Qt.AlignmentFlag.AlignLeft)

        questions_label = QLabel("Questions With High Miss Rates")
        questions_label.setContentsMargins(0, 10, 0, 0)
        main_layout.addWidget(questions_label, alignment=Qt.AlignmentFlag.AlignLeft)

        self.question_table = QTableWidget(0, 3, self)
        self.question_table.setHorizontalHeaderLabels(["Question", "% Missed", "Missed / Total"])
        self.question_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.question_table.setSelectionMode(QTableWidget.SelectionMode.MultiSelection)
        self.question_table.horizontalHeader().setStretchLastSection(True)
        main_layout.addWidget(self.question_table)

        manual_row = QWidget()
        manual_layout = QHBoxLayout(manual_row)
        manual_layout.setContentsMargins(0, 0, 0, 0)
        manual_layout.setSpacing(6)
        manual_label = QLabel("Manual questions (comma-separated):")
        self.manual_input = QLineEdit()
        self.manual_input.setPlaceholderText("e.g., Q1,Q3")
        manual_layout.addWidget(manual_label)
        manual_layout.addWidget(self.manual_input)
        main_layout.addWidget(manual_row)

        self.log_checkbox = QCheckBox("Generate adjustment log (version.log)")
        self.log_checkbox.setChecked(True)
        main_layout.addWidget(self.log_checkbox, alignment=Qt.AlignmentFlag.AlignLeft)

        version_row = QWidget()
        version_layout = QHBoxLayout(version_row)
        version_layout.setContentsMargins(0, 0, 0, 0)
        version_layout.setSpacing(6)
        version_layout.addWidget(QLabel("New version ID:"))
        self.version_input = QLineEdit()
        self.version_input.setPlaceholderText("adjustment_1")
        version_layout.addWidget(self.version_input)
        main_layout.addWidget(version_row)

        existing_row = QWidget()
        existing_layout = QHBoxLayout(existing_row)
        existing_layout.setContentsMargins(0, 0, 0, 0)
        existing_layout.setSpacing(6)
        existing_layout.addWidget(QLabel("Saved adjustments:"))
        self.version_combo = QComboBox()
        self.version_combo.currentTextChanged.connect(lambda _: self._update_review_buttons())
        existing_layout.addWidget(self.version_combo)
        main_layout.addWidget(existing_row)

        button_row = QWidget()
        button_layout = QHBoxLayout(button_row)
        button_layout.setContentsMargins(0, 0, 0, 0)
        button_layout.setSpacing(8)

        self.preview_button = QPushButton("Preview Adjusted Grades")
        self.preview_button.clicked.connect(self._preview_adjustment)
        button_layout.addWidget(self.preview_button)

        self.save_button = QPushButton("Save Adjustment")
        self.save_button.clicked.connect(self._save_adjustment)
        button_layout.addWidget(self.save_button)

        self.finalize_button = QPushButton("Finalize Grades")
        self.finalize_button.clicked.connect(self._finalize_adjustment)
        button_layout.addWidget(self.finalize_button)

        main_layout.addWidget(button_row, alignment=Qt.AlignmentFlag.AlignLeft)

        review_row = QWidget()
        review_layout = QHBoxLayout(review_row)
        review_layout.setContentsMargins(0, 0, 0, 0)
        review_layout.setSpacing(6)
        self.review_results_button = QPushButton("Review Adjusted Results")
        self.review_results_button.clicked.connect(lambda: self._open_version_file("_results.csv", "adjusted results CSV"))
        review_layout.addWidget(self.review_results_button)

        self.review_grades_csv_button = QPushButton("Review Adjusted Grades CSV")
        self.review_grades_csv_button.clicked.connect(lambda: self._open_version_file("_graded_report.csv", "adjusted grades CSV"))
        review_layout.addWidget(self.review_grades_csv_button)

        self.review_grades_xlsx_button = QPushButton("Review Adjusted Grades Excel")
        self.review_grades_xlsx_button.clicked.connect(lambda: self._open_version_file("_graded_report.xlsx", "adjusted grades workbook"))
        review_layout.addWidget(self.review_grades_xlsx_button)

        self.review_log_button = QPushButton("Review Adjustment Log")
        self.review_log_button.clicked.connect(lambda: self._open_version_file(".log", "adjustment log"))
        review_layout.addWidget(self.review_log_button)

        main_layout.addWidget(review_row, alignment=Qt.AlignmentFlag.AlignLeft)

        self.tips_button = QPushButton("Show Adjustment Tips")
        self.tips_button.clicked.connect(lambda: self.output_view.setPlainText(_ADJUSTMENT_TIPS))
        main_layout.addWidget(self.tips_button, alignment=Qt.AlignmentFlag.AlignLeft)

        output_label = QLabel("Command Output")
        output_label.setContentsMargins(0, 10, 0, 0)
        main_layout.addWidget(output_label, alignment=Qt.AlignmentFlag.AlignLeft)

        self.output_view = QTextEdit()
        mono = QFont("Courier New", 11)
        self.output_view.setFont(mono)
        self.output_view.setReadOnly(True)
        self.output_view.setMinimumHeight(220)
        main_layout.addWidget(self.output_view)

        self._update_review_buttons()

    def _make_path_display(self, label: str, layout: QFormLayout, placeholder: str) -> QLineEdit:
        line = QLineEdit()
        line.setReadOnly(True)
        line.setPlaceholderText(placeholder)
        layout.addRow(label, line)
        return line

    def _evaluate_inputs(self, show_message: bool) -> bool:
        active_folder = config.active_test_folder()
        exam_title = config.extract_exam_title()
        ok, error, results_path, key_path, miss_path = config.adjustment_inputs_active(active_folder, exam_title)
        if not ok:
            self._results_path = None
            self._answer_key_path = None
            self._miss_report_path = None
            self.results_display.setText("Not found")
            self.answer_key_display.setText("Not found")
            self.miss_report_display.setText("Not found")
            self.preview_button.setEnabled(False)
            self.save_button.setEnabled(False)
            self.finalize_button.setEnabled(False)
            if show_message:
                self.output_view.setPlainText(error or "Missing inputs. Complete earlier steps first.")
            return False

        assert results_path and key_path
        self._results_path = results_path
        self._answer_key_path = key_path
        self._miss_report_path = miss_path
        self.results_display.setText(str(results_path))
        self.answer_key_display.setText(str(key_path))
        if miss_path:
            self.miss_report_display.setText(str(miss_path))
        else:
            self.miss_report_display.setText("Not found (manual entry only)")

        self.preview_button.setEnabled(True)
        self.save_button.setEnabled(True)
        self.finalize_button.setEnabled(True)
        self._load_miss_report()
        self._update_version_placeholder()
        return True

    def _load_miss_report(self) -> None:
        rows = config.parse_miss_report(self._miss_report_path)
        self._available_questions = rows
        self.question_table.setRowCount(0)
        if not rows:
            self.output_view.append("Miss report not found or empty. Select questions manually.")
            return
        for row in rows:
            current_row = self.question_table.rowCount()
            self.question_table.insertRow(current_row)
            percent = row.get("Percent_Missed", "")
            try:
                percent_value = float(percent)
            except ValueError:
                percent_value = 0.0
            question_item = QTableWidgetItem(row["Question"])
            percent_item = QTableWidgetItem(percent)
            detail = f"{row.get('Missed_Count','')} / {row.get('Total_Students','')}"
            detail_item = QTableWidgetItem(detail.strip())
            if percent_value >= 50.0:
                question_item.setBackground(Qt.GlobalColor.yellow)
                percent_item.setBackground(Qt.GlobalColor.yellow)
                detail_item.setBackground(Qt.GlobalColor.yellow)
            self.question_table.setItem(current_row, 0, question_item)
            self.question_table.setItem(current_row, 1, percent_item)
            self.question_table.setItem(current_row, 2, detail_item)
        self.question_table.resizeColumnsToContents()

    def _gather_question_ids(self) -> list[str]:
        questions: set[str] = set()
        for index in self.question_table.selectionModel().selectedRows():
            text = self.question_table.item(index.row(), 0).text()
            normalized = config.normalize_question_id(text)
            if normalized:
                questions.add(normalized)
        manual_text = self.manual_input.text().strip()
        if manual_text:
            for token in manual_text.split(","):
                normalized = config.normalize_question_id(token)
                if normalized:
                    questions.add(normalized)
        if not questions:
            raise ValueError("Select at least one question or enter IDs manually (e.g., Q1,Q3).")
        return sorted(questions)

    def _preview_adjustment(self) -> None:
        if not self._evaluate_inputs(show_message=False):
            QMessageBox.warning(self, "Missing inputs", "Ensure results, answer key, and miss report exist.")
            return
        try:
            questions = self._gather_question_ids()
        except ValueError as exc:
            QMessageBox.warning(self, "Select questions", str(exc))
            return
        command = [
            str(config.PYTHON_EXECUTABLE),
            str(self._script_path),
            "--results",
            str(self._results_path),
            "--key",
            str(self._answer_key_path),
            "--give-back",
            ",".join(questions),
        ]
        with tempfile.TemporaryDirectory(prefix="preview_adjustment") as tmp_dir:
            tmp_path = Path(tmp_dir)
            command.extend(["--version", "preview", "--output-dir", str(tmp_path)])
            self.output_view.append(f"$ {' '.join(shlex_quote(part) for part in command)}\n")
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                cwd=str(config.CLI_PATH),
            )
            if result.returncode != 0:
                self.output_view.append(result.stdout)
                self.output_view.append(result.stderr)
                QMessageBox.critical(
                    self,
                    "Preview failed",
                    "The CLI command reported an error. See the output panel for details.",
                )
                return
            preview_lines = result.stdout.strip() or "Preview completed."
            self.output_view.append(preview_lines + "\n(Preview files stored in a temporary folder.)\n")

    def _save_adjustment(self) -> None:
        if not self._evaluate_inputs(show_message=False):
            QMessageBox.warning(self, "Missing inputs", "Ensure results, answer key, and miss report exist.")
            return
        try:
            questions = self._gather_question_ids()
        except ValueError as exc:
            QMessageBox.warning(self, "Select questions", str(exc))
            return
        version = self.version_input.text().strip() or config.next_adjustment_version(config.active_test_folder())
        if not version:
            version = config.next_adjustment_version(config.active_test_folder())
        if not config.is_valid_version_label(version):
            QMessageBox.warning(
                self,
                "Invalid version name",
                "Version label may only contain letters, numbers, underscores, or hyphens.",
            )
            return
        active_folder = config.active_test_folder()
        assert active_folder
        adjustments_dir = active_folder / "adjustments"
        adjustments_dir.mkdir(parents=True, exist_ok=True)
        command = [
            str(config.PYTHON_EXECUTABLE),
            str(self._script_path),
            "--results",
            str(self._results_path),
            "--key",
            str(self._answer_key_path),
            "--give-back",
            ",".join(questions),
            "--version",
            version,
            "--output-dir",
            str(adjustments_dir),
        ]
        if self.log_checkbox.isChecked():
            command.extend(["--log", str(adjustments_dir / f"{version}.log")])
        self.output_view.append(f"$ {' '.join(shlex_quote(part) for part in command)}\n")
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            cwd=str(config.CLI_PATH),
        )
        if result.returncode != 0:
            self.output_view.append(result.stdout)
            self.output_view.append(result.stderr)
            QMessageBox.critical(
                self,
                "Adjustment failed",
                "The CLI command reported an error. See the output panel for details.",
            )
            return
        if result.stdout.strip():
            self.output_view.append(result.stdout.strip())
        self.output_view.append(f"Saved adjustment '{version}'.\n")
        self._refresh_versions(select_version=version)

    def _finalize_adjustment(self) -> None:
        version = self.version_combo.currentText().strip()
        if not version:
            QMessageBox.information(self, "Select a version", "Choose an adjustment version to finalize.")
            return
        reply = QMessageBox.question(
            self,
            "Finalize grades",
            f"Copy {version}_graded_report.* into grades/? This will overwrite the official grades.",
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        active_folder = config.active_test_folder()
        assert active_folder
        adjustments_dir = active_folder / "adjustments"
        grades_dir = active_folder / "grades"
        grades_dir.mkdir(parents=True, exist_ok=True)
        src_csv = adjustments_dir / f"{version}_graded_report.csv"
        src_xlsx = adjustments_dir / f"{version}_graded_report.xlsx"
        if not src_csv.exists() or not src_xlsx.exists():
            QMessageBox.warning(
                self,
                "Files missing",
                f"Could not find {version}_graded_report.csv/.xlsx. Save the adjustment first.",
            )
            return
        dst_csv = grades_dir / "graded_report.csv"
        dst_xlsx = grades_dir / "graded_report.xlsx"
        src_csv.replace(dst_csv)
        src_xlsx.replace(dst_xlsx)
        self.output_view.append(f"Finalized grades from {version} into {grades_dir}.\n")
        QMessageBox.information(self, "Grades finalized", f"{version} copied into grades/.")

    def _refresh_versions(self, select_version: str | None = None) -> None:
        active_folder = config.active_test_folder()
        self._versions = config.list_adjustment_versions(active_folder)
        self.version_combo.blockSignals(True)
        self.version_combo.clear()
        self.version_combo.addItems(self._versions)
        if select_version and select_version in self._versions:
            index = self._versions.index(select_version)
            self.version_combo.setCurrentIndex(index)
        self.version_combo.blockSignals(False)
        self._update_review_buttons()
        self._update_version_placeholder()

    def _update_version_placeholder(self) -> None:
        active_folder = config.active_test_folder()
        suggestion = config.next_adjustment_version(active_folder)
        if not self.version_input.text().strip():
            self.version_input.setPlaceholderText(suggestion)

    def _update_review_buttons(self) -> None:
        version = self.version_combo.currentText().strip()
        active_folder = config.active_test_folder()
        if not version or not active_folder:
            for button in (
                self.review_results_button,
                self.review_grades_csv_button,
                self.review_grades_xlsx_button,
                self.review_log_button,
            ):
                button.setEnabled(False)
            return
        adjustments_dir = active_folder / "adjustments"
        self.review_results_button.setEnabled((adjustments_dir / f"{version}_results.csv").exists())
        self.review_grades_csv_button.setEnabled((adjustments_dir / f"{version}_graded_report.csv").exists())
        self.review_grades_xlsx_button.setEnabled((adjustments_dir / f"{version}_graded_report.xlsx").exists())
        self.review_log_button.setEnabled((adjustments_dir / f"{version}.log").exists())

    def _open_version_file(self, suffix: str, label: str) -> None:
        version = self.version_combo.currentText().strip()
        active_folder = config.active_test_folder()
        if not version or not active_folder:
            QMessageBox.information(self, "Select a version", "Choose a saved adjustment first.")
            return
        adjustments_dir = active_folder / "adjustments"
        path = adjustments_dir / f"{version}{suffix}"
        if not path.exists():
            QMessageBox.information(self, "File not found", f"{label} for {version} does not exist.")
            return
        self._open_path(path, label)

    def _open_path(self, path: Path, label: str) -> None:
        try:
            if sys.platform.startswith("win"):
                subprocess.Popen(["cmd", "/c", "start", "", str(path)])
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path)])
        except OSError as exc:  # noqa: PERF203
            QMessageBox.critical(self, "Viewer error", f"Could not open {label}: {exc}")

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._evaluate_inputs(show_message=False)
        self._refresh_versions()
