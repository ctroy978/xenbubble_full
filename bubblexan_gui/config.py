"""Shared configuration for the Bubblexan GUI."""

from __future__ import annotations

import sys
from pathlib import Path

GUI_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = GUI_ROOT.parent
CLI_PATH = (PROJECT_ROOT / "bubblexan_cli").resolve()

_CLI_SCRIPTS = [
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


def _validate_paths() -> None:
    for script in _CLI_SCRIPTS:
        script_path = CLI_PATH / script
        if not script_path.exists():
            raise FileNotFoundError(
                f"Expected CLI script at '{script_path}'. Make sure bubblexan_cli is set up."
            )

    if not PYTHON_EXECUTABLE.exists():
        raise FileNotFoundError(
            "Python executable for the CLI venv was not found at "
            f"'{PYTHON_EXECUTABLE}'. Activate bubblexan_cli/.venv and install dependencies."
        )


_validate_paths()

__all__ = [
    "CLI_PATH",
    "PYTHON_EXECUTABLE",
    "PROJECT_ROOT",
]
