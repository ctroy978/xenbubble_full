"""Configuration helpers for the Bubblexan Test Manager GUI."""

from __future__ import annotations

import csv
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Iterable

GUI_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = GUI_ROOT.parent
CLI_PATH = (PROJECT_ROOT / "bubblexan_cli").resolve()
TEST_BUILD_PATH = (PROJECT_ROOT / "test_build").resolve()

_REQUIRED_CLI_SCRIPTS = [
    "generate_bubblesheet.py",
    "generate_test_from_qti.py",
    "convert_pdf_to_png.py",
    "scan_bubblesheet.py",
    "grade.py",
    "analyze_misses.py",
]

_VENV_DIR = CLI_PATH / ".venv"
_VENV_BIN = _VENV_DIR / ("Scripts" if sys.platform == "win32" else "bin")
PYTHON_EXECUTABLE = _VENV_BIN / ("python.exe" if sys.platform == "win32" else "python")

ACTIVE_TEST_NAME: str | None = None


def validate_cli_environment(required_scripts: Iterable[str] | None = None) -> None:
    """Ensure the CLI folder, scripts, and test build path exist."""

    scripts_to_check = list(required_scripts or _REQUIRED_CLI_SCRIPTS)

    if not CLI_PATH.exists():
        raise FileNotFoundError(
            f"Expected CLI directory at '{CLI_PATH}'. Verify the bubblexan_cli checkout."
        )

    missing_scripts = [script for script in scripts_to_check if not (CLI_PATH / script).exists()]
    if missing_scripts:
        formatted = ", ".join(missing_scripts)
        raise FileNotFoundError(
            "Missing CLI scripts: "
            f"{formatted}. Confirm the repository is complete."
        )

    TEST_BUILD_PATH.mkdir(parents=True, exist_ok=True)


def extract_exam_title(folder_name: str | None = None) -> str | None:
    """Return the instructor-provided exam title without the timestamp suffix."""

    candidate = folder_name or ACTIVE_TEST_NAME
    if not candidate:
        return None
    parts = candidate.rsplit("_", 2)
    if len(parts) != 3:
        return candidate or None
    title = parts[0]
    return title or None


def active_test_folder() -> Path | None:
    """Return the full path to the active test folder, if any."""

    if not ACTIVE_TEST_NAME:
        return None
    return TEST_BUILD_PATH / ACTIVE_TEST_NAME


validate_cli_environment()

_META_NAME = "assessment_meta.xml"
_MANIFEST_NAME = "imsmanifest.xml"
_ANSWER_HEADERS = ["Question", "Correct_Answer", "Points"]
_QUESTION_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")
_ANSWER_PATTERN = re.compile(r"^[a-e]$")
_VERSION_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")
_PDF_EXTENSIONS = {".pdf"}
_PNG_EXTENSIONS = {".png"}


def _find_case_insensitive(folder: Path, target_name: str) -> Path | None:
    target_lower = target_name.lower()
    for path in folder.rglob("*"):
        if path.is_file() and path.name.lower() == target_lower:
            return path
    return None


def find_primary_qti_xml(folder: Path) -> Path | None:
    """Return the first XML file that is not assessment_meta or manifest."""

    for path in folder.rglob("*.xml"):
        name = path.name.lower()
        if name in {_META_NAME, _MANIFEST_NAME}:
            continue
        return path
    return None


def find_qti_support_files(folder: Path) -> tuple[Path | None, Path | None]:
    """Return assessment_meta and imsmanifest paths if they exist."""

    return (
        _find_case_insensitive(folder, _META_NAME),
        _find_case_insensitive(folder, _MANIFEST_NAME),
    )


def validate_qti_source(source: Path) -> list[str]:
    """Validate that a folder or ZIP contains required QTI files."""

    path = Path(source).expanduser()
    if not path.exists():
        return ["Selected path does not exist."]
    if path.is_file():
        if path.suffix.lower() != ".zip":
            return ["Selected file must be a .zip archive."]
        return _validate_zip_contents(path)
    if path.is_dir():
        return _validate_folder_contents(path)
    return ["Selected path must be a folder or .zip file."]


def _validate_folder_contents(folder: Path) -> list[str]:
    missing: list[str] = []
    if not find_primary_qti_xml(folder):
        missing.append("QTI XML file (.xml)")
    if not _find_case_insensitive(folder, _META_NAME):
        missing.append(_META_NAME)
    if not _find_case_insensitive(folder, _MANIFEST_NAME):
        missing.append(_MANIFEST_NAME)
    return missing


def _validate_zip_contents(zip_path: Path) -> list[str]:
    with tempfile.TemporaryDirectory() as tmp_dir:
        with zipfile.ZipFile(zip_path) as archive:
            archive.extractall(tmp_dir)
        extracted_root = Path(tmp_dir)
        return _validate_folder_contents(extracted_root)


def validate_answer_key(csv_path: Path) -> list[str]:
    """Validate the structure of a manually provided answer key CSV."""

    path = Path(csv_path).expanduser()
    errors: list[str] = []
    if not path.exists():
        return ["Selected CSV file does not exist."]
    if path.suffix.lower() != ".csv":
        return ["Selected file must have a .csv extension."]

    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            headers = reader.fieldnames or []
            missing_headers = [header for header in _ANSWER_HEADERS if header not in headers]
            if missing_headers:
                return [f"Missing header '{name}'." for name in missing_headers]

            for row_number, row in enumerate(reader, start=2):
                if not row:
                    errors.append(f"Row {row_number} is empty.")
                    continue

                question = (row.get("Question") or "").strip()
                answer = (row.get("Correct_Answer") or "").strip()
                points_raw = (row.get("Points") or "").strip()

                if not question:
                    errors.append(f"Row {row_number}: Question cannot be empty.")
                elif not _QUESTION_PATTERN.fullmatch(question):
                    errors.append(
                        f"Row {row_number}: Question '{question}' must use letters, numbers, underscores, or hyphens."
                    )

                if not answer:
                    errors.append(f"Row {row_number}: Correct_Answer cannot be empty.")
                else:
                    segments = answer.split(",")
                    for segment in segments:
                        if not _ANSWER_PATTERN.fullmatch(segment):
                            errors.append(
                                f"Row {row_number}: Correct_Answer '{answer}' must use letters a-e with commas and no spaces."
                            )
                            break

                if not points_raw:
                    errors.append(f"Row {row_number}: Points cannot be empty.")
                else:
                    try:
                        points_value = float(points_raw)
                        if points_value <= 0:
                            errors.append(f"Row {row_number}: Points must be greater than zero.")
                    except ValueError:
                        errors.append(f"Row {row_number}: Points '{points_raw}' is not a valid number.")

    except csv.Error as exc:
        errors.append(f"CSV parsing error: {exc}")

    return errors


def validate_pdf_input(source: Path) -> list[str]:
    """Ensure the selected PDF/ZIP/folder contains at least one PDF."""

    path = Path(source).expanduser()
    if not path.exists():
        return ["Selected path does not exist."]

    if path.is_file():
        suffix = path.suffix.lower()
        if suffix == ".pdf":
            return []
        if suffix == ".zip":
            with zipfile.ZipFile(path) as archive:
                if any(
                    not info.is_dir() and info.filename.lower().endswith(tuple(_PDF_EXTENSIONS))
                    for info in archive.infolist()
                ):
                    return []
            return ["ZIP archive does not contain any PDF files."]
        return ["Selected file must be a .pdf or .zip archive."]

    if path.is_dir():
        if any(pdf.suffix.lower() in _PDF_EXTENSIONS for pdf in path.rglob("*.pdf")):
            return []
        return ["Folder does not contain any PDF files."]

    return ["Selected path must be a file or folder."]


def poppler_available() -> bool:
    """Return True if pdftoppm (Poppler) is available on PATH."""

    if shutil.which("pdftoppm"):
        return True
    try:
        subprocess.run(
            ["pdftoppm", "-h"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True
    except FileNotFoundError:
        return False


def layout_json_path(active_folder: Path | None, exam_title: str | None) -> Path | None:
    """Return the expected layout JSON path for the active test."""

    if not active_folder or not exam_title:
        return None
    return active_folder / "bubble_sheets" / f"{exam_title}_layout.json"


def validate_scanner_inputs(source: Path, layout_path: Path) -> tuple[bool, str | None]:
    """Validate that scanner inputs exist and contain PNG files."""

    if not layout_path.exists():
        return False, f"Layout JSON not found: {layout_path}"

    path = Path(source).expanduser()
    if not path.exists():
        return False, f"Selected path does not exist: {path}"

    if path.is_file():
        suffix = path.suffix.lower()
        if suffix == ".zip":
            with zipfile.ZipFile(path) as archive:
                for info in archive.infolist():
                    if info.is_dir():
                        continue
                    if info.filename.lower().endswith(".png"):
                        return True, None
            return False, "ZIP archive does not contain any PNG files."
        if suffix in _PNG_EXTENSIONS:
            return True, None
        return False, "Selected file must be a .png image or .zip archive."

    if path.is_dir():
        if any(file.suffix.lower() in _PNG_EXTENSIONS for file in path.rglob("*.png")):
            return True, None
        return False, "Folder does not contain any PNG files."

    return False, "Selected path must be a file or folder."


def grade_inputs_active(active_folder: Path | None, exam_title: str | None) -> tuple[bool, str | None, Path | None, Path | None]:
    """Check for required inputs (results.csv, answer_key.csv) and return their paths."""

    if not active_folder or not exam_title:
        return False, "No test selected.", None, None

    results_path = active_folder / "results" / "results.csv"
    key_path = active_folder / "tests" / f"{exam_title}_answer_key.csv"

    if not results_path.exists():
        return False, f"Missing results CSV at {results_path}. Run the Bubble Sheet Scanner tab first.", None, None
    if not key_path.exists():
        return False, f"Missing answer key CSV at {key_path}. Generate or import an answer key first.", None, None
    return True, None, results_path, key_path


def adjustment_inputs_active(
    active_folder: Path | None,
    exam_title: str | None,
) -> tuple[bool, str | None, Path | None, Path | None, Path | None]:
    """Ensure results, answer key, and (optionally) miss_report exist."""

    ok, error, results_path, key_path = grade_inputs_active(active_folder, exam_title)
    if not ok:
        return False, error, None, None, None

    miss_report_path: Path | None = None
    if active_folder:
        candidate = active_folder / "miss_analysis" / "miss_report.csv"
        if candidate.exists():
            miss_report_path = candidate
    return True, None, results_path, key_path, miss_report_path


def parse_miss_report(miss_report_path: Path | None) -> list[dict[str, str]]:
    """Parse miss_report.csv rows."""

    if not miss_report_path or not miss_report_path.exists():
        return []
    rows: list[dict[str, str]] = []
    with miss_report_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            return []
        for line in reader:
            if not line:
                continue
            question = (line.get("Question") or "").strip()
            percent = (line.get("Percent_Missed") or "").strip()
            missed = (line.get("Missed_Count") or "").strip()
            total = (line.get("Total_Students") or "").strip()
            if not question:
                continue
            rows.append(
                {
                    "Question": question.upper(),
                    "Percent_Missed": percent,
                    "Missed_Count": missed,
                    "Total_Students": total,
                }
            )
    return rows


def list_adjustment_versions(active_folder: Path | None) -> list[str]:
    """Return sorted list of adjustment version names."""

    if not active_folder:
        return []
    adjustments_dir = active_folder / "adjustments"
    if not adjustments_dir.exists():
        return []
    versions = set()
    for csv_file in adjustments_dir.glob("*_results.csv"):
        name = csv_file.stem
        if name.endswith("_results"):
            versions.add(name[: -len("_results")])
    return sorted(versions)


def next_adjustment_version(active_folder: Path | None) -> str:
    """Suggest the next adjustment version name."""

    existing = list_adjustment_versions(active_folder)
    prefix = "adjustment"
    if not existing:
        return f"{prefix}_1"
    max_index = 0
    for version in existing:
        if version.startswith(f"{prefix}_"):
            try:
                value = int(version.split("_")[-1])
            except ValueError:
                continue
            max_index = max(max_index, value)
    return f"{prefix}_{max_index + 1}"


def normalize_question_id(raw: str) -> str:
    """Normalize question IDs to uppercase 'Q' format."""

    text = raw.strip()
    if not text:
        return ""
    if not text.upper().startswith("Q"):
        return f"Q{text.upper()}"
    suffix = text[1:].strip()
    return f"Q{suffix.upper()}" if suffix else "Q"


def is_valid_version_label(value: str) -> bool:
    """Validate adjustment version labels."""

    if not value:
        return False
    return bool(_VERSION_PATTERN.fullmatch(value.strip()))


__all__ = [
    "ACTIVE_TEST_NAME",
    "CLI_PATH",
    "GUI_ROOT",
    "PROJECT_ROOT",
    "PYTHON_EXECUTABLE",
    "TEST_BUILD_PATH",
    "active_test_folder",
    "extract_exam_title",
    "find_primary_qti_xml",
    "find_qti_support_files",
    "validate_answer_key",
    "validate_pdf_input",
    "validate_scanner_inputs",
    "grade_inputs_active",
    "adjustment_inputs_active",
    "layout_json_path",
    "parse_miss_report",
    "list_adjustment_versions",
    "next_adjustment_version",
    "normalize_question_id",
    "is_valid_version_label",
    "is_valid_version_label",
    "poppler_available",
    "validate_cli_environment",
    "validate_qti_source",
]
