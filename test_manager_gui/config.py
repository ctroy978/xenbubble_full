"""Configuration helpers for the Bubblexan Test Manager GUI."""

from __future__ import annotations

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
    "validate_cli_environment",
    "validate_qti_source",
]
