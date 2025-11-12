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
    QSizePolicy,
    QMenu,
    QFileDialog,
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
        self._inputs_valid = False
        self._last_selection_tokens: set[str] = set()
        self._suspend_selection_sync = False
        self._init_ui()
        self._evaluate_inputs(show_message=True)
        self._refresh_versions()

    def _init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 10, 10, 10)

        questions_label = QLabel("Questions With High Miss Rates")
        questions_label.setContentsMargins(0, 10, 0, 0)
        main_layout.addWidget(questions_label, alignment=Qt.AlignmentFlag.AlignLeft)

        self.question_table = QTableWidget(0, 3, self)
        self.question_table.setHorizontalHeaderLabels(["Question", "% Missed", "Missed / Total"])
        self.question_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.question_table.setSelectionMode(QTableWidget.SelectionMode.MultiSelection)
        self.question_table.horizontalHeader().setStretchLastSection(True)
        self.question_table.setMinimumHeight(200)
        self.question_table.setMaximumHeight(240)
        self.question_table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.MinimumExpanding)
        main_layout.addWidget(self.question_table)

        version_row = QWidget()
        version_layout = QHBoxLayout(version_row)
        version_layout.setContentsMargins(0, 0, 0, 0)
        version_layout.setSpacing(12)

        manual_group = QWidget()
        manual_group_layout = QHBoxLayout(manual_group)
        manual_group_layout.setContentsMargins(0, 0, 0, 0)
        manual_group_layout.setSpacing(6)
        manual_label = QLabel("Give back questions (comma-separated):")
        manual_label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        self.manual_input = QLineEdit()
        self.manual_input.setPlaceholderText("e.g., Q1,Q3")
        self.manual_input.setFixedWidth(220)
        manual_group_layout.addWidget(manual_label)
        manual_group_layout.addWidget(self.manual_input)
        manual_group_layout.addStretch()
        version_layout.addWidget(manual_group)

        version_group = QWidget()
        version_group_layout = QHBoxLayout(version_group)
        version_group_layout.setContentsMargins(0, 0, 0, 0)
        version_group_layout.setSpacing(6)
        version_label = QLabel("New version ID:")
        version_label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        version_group_layout.addWidget(version_label)
        self.version_input = QLineEdit()
        self.version_input.setPlaceholderText("adjustment_1")
        self.version_input.setFixedWidth(160)
        version_group_layout.addWidget(self.version_input)
        version_group_layout.addStretch()
        version_layout.addWidget(version_group)
        version_layout.addStretch()
        main_layout.addWidget(version_row)
        self.question_table.itemSelectionChanged.connect(self._sync_manual_selection)

        existing_row = QWidget()
        existing_layout = QHBoxLayout(existing_row)
        existing_layout.setContentsMargins(0, 0, 0, 0)
        existing_layout.setSpacing(6)
        existing_layout.addWidget(QLabel("Saved adjustments:"))
        self.version_combo = QComboBox()
        self.version_combo.setMinimumContentsLength(20)
        self.version_combo.currentTextChanged.connect(lambda _: self._update_review_buttons())
        existing_layout.addWidget(self.version_combo)
        existing_layout.addStretch()
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
        self.review_adjusted_button = QPushButton("Review Adjusted Files")
        self.review_menu = QMenu(self.review_adjusted_button)
        self.review_results_action = self.review_menu.addAction("Adjusted Results CSV")
        self.review_results_action.triggered.connect(
            lambda: self._open_version_file("_results.csv", "adjusted results CSV")
        )
        self.review_grades_csv_action = self.review_menu.addAction("Adjusted Grades CSV")
        self.review_grades_csv_action.triggered.connect(
            lambda: self._open_version_file("_graded_report.csv", "adjusted grades CSV")
        )
        self.review_grades_xlsx_action = self.review_menu.addAction("Adjusted Grades Excel")
        self.review_grades_xlsx_action.triggered.connect(
            lambda: self._open_version_file("_graded_report.xlsx", "adjusted grades workbook")
        )
        self.review_adjusted_button.setMenu(self.review_menu)
        review_layout.addWidget(self.review_adjusted_button)

        self.view_final_button = QPushButton("View Final Grades")
        self.final_menu = QMenu(self.view_final_button)
        self.final_csv_action = self.final_menu.addAction("Open Final Grades CSV")
        self.final_csv_action.triggered.connect(lambda: self._open_final_grade("csv"))
        self.final_xlsx_action = self.final_menu.addAction("Open Final Grades Excel")
        self.final_xlsx_action.triggered.connect(lambda: self._open_final_grade("xlsx"))
        self.view_final_button.setMenu(self.final_menu)
        review_layout.addWidget(self.view_final_button)

        self.export_canvas_button = QPushButton("Export Canvas Grades")
        self.export_canvas_button.clicked.connect(self._export_canvas_grades)
        review_layout.addWidget(self.export_canvas_button)

        main_layout.addWidget(review_row, alignment=Qt.AlignmentFlag.AlignLeft)

        tips_row = QWidget()
        tips_layout = QHBoxLayout(tips_row)
        tips_layout.setContentsMargins(0, 0, 0, 0)
        tips_layout.setSpacing(6)

        self.tips_button = QPushButton("Show Adjustment Tips")
        self.tips_button.clicked.connect(lambda: self.output_view.setPlainText(_ADJUSTMENT_TIPS))
        tips_layout.addWidget(self.tips_button)

        self.review_log_button = QPushButton("Review Adjustment Log")
        self.review_log_button.clicked.connect(lambda: self._open_version_file(".log", "adjustment log"))
        tips_layout.addWidget(self.review_log_button)
        tips_layout.addStretch()

        main_layout.addWidget(tips_row, alignment=Qt.AlignmentFlag.AlignLeft)

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
        self._update_final_grade_controls()

    def _evaluate_inputs(self, show_message: bool) -> bool:
        active_folder = config.active_test_folder()
        exam_title = config.extract_exam_title()
        ok, error, results_path, key_path, miss_path = config.adjustment_inputs_active(active_folder, exam_title)
        if not ok:
            self._results_path = None
            self._answer_key_path = None
            self._miss_report_path = None
            self.preview_button.setEnabled(False)
            self.save_button.setEnabled(False)
            self.finalize_button.setEnabled(False)
            self.view_final_button.setEnabled(False)
            self.export_canvas_button.setEnabled(False)
            self._inputs_valid = False
            if show_message:
                self.output_view.setPlainText(error or "Missing inputs. Complete earlier steps first.")
            return False

        assert results_path and key_path
        self._results_path = results_path
        self._answer_key_path = key_path
        self._miss_report_path = miss_path

        self.preview_button.setEnabled(True)
        self.save_button.setEnabled(True)
        self.finalize_button.setEnabled(True)
        self._inputs_valid = True
        self._load_miss_report()
        self._update_version_placeholder()
        self._update_final_grade_controls()
        return True

    def _load_miss_report(self) -> None:
        self._suspend_selection_sync = True
        rows = config.parse_miss_report(self._miss_report_path)
        self._available_questions = rows
        self.question_table.setRowCount(0)
        if not rows:
            self.output_view.append("Miss report not found or empty. Select questions manually.")
            self._suspend_selection_sync = False
            self._last_selection_tokens.clear()
            self.manual_input.clear()
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
        self.question_table.clearSelection()
        self._suspend_selection_sync = False
        self._last_selection_tokens.clear()
        self._sync_manual_selection()

    def _ensure_inputs_ready(self, show_message: bool) -> bool:
        if self._inputs_valid and self._results_path and self._answer_key_path:
            return True
        return self._evaluate_inputs(show_message=show_message)

    def _gather_question_ids(self) -> list[str]:
        questions: set[str] = set()
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
        if not self._ensure_inputs_ready(show_message=False):
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
        if not self._ensure_inputs_ready(show_message=False):
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
        self._update_final_grade_button()

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
        self._update_final_grade_controls()
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
            self.review_adjusted_button.setEnabled(False)
            self.review_log_button.setEnabled(False)
            return
        adjustments_dir = active_folder / "adjustments"
        has_results = (adjustments_dir / f"{version}_results.csv").exists()
        has_csv = (adjustments_dir / f"{version}_graded_report.csv").exists()
        has_xlsx = (adjustments_dir / f"{version}_graded_report.xlsx").exists()
        any_adjusted = has_results or has_csv or has_xlsx
        self.review_adjusted_button.setEnabled(any_adjusted)
        self.review_results_action.setEnabled(has_results)
        self.review_grades_csv_action.setEnabled(has_csv)
        self.review_grades_xlsx_action.setEnabled(has_xlsx)
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

    def _sync_manual_selection(self) -> None:
        if self._suspend_selection_sync or self.manual_input is None:
            return
        selection_model = self.question_table.selectionModel()
        if selection_model is None:
            return
        selection_tokens: set[str] = set()
        for index in selection_model.selectedRows():
            item = self.question_table.item(index.row(), 0)
            if not item:
                continue
            normalized = config.normalize_question_id(item.text())
            if normalized:
                selection_tokens.add(normalized)
        current_manual_tokens: set[str] = set()
        manual_text = self.manual_input.text().strip()
        if manual_text:
            for token in manual_text.split(","):
                normalized = config.normalize_question_id(token)
                if normalized:
                    current_manual_tokens.add(normalized)
        manual_extras = {token for token in current_manual_tokens if token not in self._last_selection_tokens}
        combined = sorted(manual_extras | selection_tokens)
        new_text = ",".join(combined)
        self._last_selection_tokens = selection_tokens
        self.manual_input.blockSignals(True)
        self.manual_input.setText(new_text)
        self.manual_input.blockSignals(False)

    def _open_final_grade(self, ext: str) -> None:
        active_folder = config.active_test_folder()
        if not active_folder:
            QMessageBox.information(self, "No active test", "Select or create a test folder first.")
            return
        grades_dir = active_folder / "grades"
        target = grades_dir / f"graded_report.{ext}"
        if not target.exists():
            QMessageBox.information(
                self,
                "Final grades missing",
                f"graded_report.{ext} not found in {grades_dir}. Finalize grades first.",
            )
            return
        self._open_path(target, f"final grades ({ext.upper()})")

    def _export_canvas_grades(self) -> None:
        active_folder = config.active_test_folder()
        if not active_folder:
            QMessageBox.information(self, "No active test", "Select or create a test folder first.")
            return
        grades_dir = active_folder / "grades"
        graded_report = grades_dir / "graded_report.csv"
        if not graded_report.exists():
            QMessageBox.information(
                self,
                "Final grades missing",
                f"{graded_report.name} not found. Finalize grades before exporting.",
            )
            return
        try:
            totals = self._collect_canvas_totals(graded_report)
        except (OSError, ValueError, csv.Error) as exc:  # noqa: PERF203
            QMessageBox.critical(self, "Export failed", f"Could not read final grades: {exc}")
            return
        if not totals:
            QMessageBox.information(self, "No data", "Final grades file is empty. Nothing to export.")
            return
        exam_name = self._canvas_exam_name()
        default_path = Path.home() / self._canvas_export_filename(exam_name)
        selected_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Canvas Export",
            str(default_path),
            "CSV Files (*.csv)",
        )
        if not selected_path:
            return
        export_path = Path(selected_path)
        try:
            with export_path.open("w", newline="", encoding="utf-8") as fp:
                writer = csv.writer(fp)
                writer.writerow(["Student ID", exam_name])
                for student_id, score in sorted(totals.items()):
                    writer.writerow([student_id, score])
        except OSError as exc:  # noqa: PERF203
            QMessageBox.critical(self, "Export failed", f"Could not write Canvas CSV: {exc}")
            return
        self.output_view.append(f"Canvas export saved to {export_path}.\n")
        QMessageBox.information(
            self,
            "Canvas export created",
            f"Saved Canvas-compatible CSV to:\n{export_path}",
        )

    def _collect_canvas_totals(self, graded_report: Path) -> dict[str, str]:
        totals: dict[str, str] = {}
        with graded_report.open("r", newline="", encoding="utf-8") as fp:
            reader = csv.DictReader(fp)
            headers = [name.strip() for name in (reader.fieldnames or []) if name]
            expected = {"student_id", "total_score"}
            missing = expected - set(headers)
            if missing:
                raise ValueError(f"{graded_report.name} missing columns: {', '.join(sorted(missing))}")
            for row in reader:
                student_id = (row.get("student_id") or "").strip()
                if not student_id:
                    continue
                total_raw = (row.get("total_score") or "").strip()
                if not total_raw:
                    totals.setdefault(student_id, "")
                    continue
                try:
                    total_value = float(total_raw)
                except ValueError as exc:
                    raise ValueError(f"Invalid total score '{total_raw}' for student {student_id}.") from exc
                totals[student_id] = self._format_canvas_score(total_value)
        return totals

    def _format_canvas_score(self, value: float) -> str:
        if value.is_integer():
            return str(int(value))
        text = f"{value:.2f}".rstrip("0").rstrip(".")
        return text or "0"

    def _canvas_exam_name(self) -> str:
        active_name = config.ACTIVE_TEST_NAME or ""
        extracted = config.extract_exam_title(active_name) if active_name else config.extract_exam_title()
        base = (extracted or active_name or "Exam").strip()
        if not base:
            base = "Exam"
        reserved = {"Current Score", "Current Grade", "Final Score", "Final Grade"}
        if base in reserved:
            base = f"{base} Export"
        return base

    def _canvas_export_filename(self, exam_name: str) -> str:
        safe = "".join(ch if ch.isalnum() else "_" for ch in exam_name)
        safe = "_".join(filter(None, safe.split("_")))
        if not safe:
            safe = "canvas_export"
        return f"{safe.lower()}_canvas_export.csv"

    def _update_final_grade_controls(self) -> None:
        active_folder = config.active_test_folder()
        if not active_folder:
            self.view_final_button.setEnabled(False)
            self.export_canvas_button.setEnabled(False)
            return
        grades_dir = active_folder / "grades"
        has_csv = (grades_dir / "graded_report.csv").exists()
        has_xlsx = (grades_dir / "graded_report.xlsx").exists()
        self.view_final_button.setEnabled(has_csv or has_xlsx)
        self.final_csv_action.setEnabled(has_csv)
        self.final_xlsx_action.setEnabled(has_xlsx)
        self.export_canvas_button.setEnabled(has_csv)

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._evaluate_inputs(show_message=False)
        self._refresh_versions()
