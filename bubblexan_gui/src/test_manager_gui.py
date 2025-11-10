"""UI for managing test folder structures."""

from __future__ import annotations

import os
import re
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFormLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from config import PROJECT_ROOT, TEST_BUILD_PATH

VALID_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

SUBDIRECTORIES = [
    "inputs",
    "inputs/scans",
    "bubble_sheets",
    "tests",
    "scanned_images",
    "results",
    "grades",
    "miss_analysis",
    "adjustments",
]


class TestManagerGui(QWidget):
    """Creates structured folders for each test."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 10, 10, 10)

        form_widget = QWidget(self)
        form_widget.setMaximumWidth(520)
        form_layout = QFormLayout(form_widget)

        self.test_name_input = QLineEdit()
        self.test_name_input.setPlaceholderText("e.g., exam_1_class2")
        self.test_name_input.setToolTip("Enter a folder name for this test, e.g., exam_1_class2.")
        form_layout.addRow("Test Name:", self.test_name_input)

        layout.addWidget(form_widget, alignment=Qt.AlignmentFlag.AlignLeft)

        self.create_button = QPushButton("Create Test Folder")
        self.create_button.setFixedWidth(220)
        self.create_button.setToolTip("Create the folder structure for this test.")
        self.create_button.clicked.connect(self._create_structure)
        layout.addWidget(self.create_button, alignment=Qt.AlignmentFlag.AlignLeft)

        output_label = QTextEdit()
        output_label.hide()

        self.output_view = QTextEdit()
        self.output_view.setReadOnly(True)
        self.output_view.setMinimumHeight(220)
        self.output_view.setToolTip("Created folders will be listed here.")
        layout.addWidget(self.output_view)

        layout.addStretch()

    def _validate_name(self, name: str) -> None:
        if not name:
            raise ValueError("Test name cannot be empty.")
        if "/" in name or "\\" in name:
            raise ValueError("Test name cannot contain path separators.")
        if not VALID_NAME_PATTERN.match(name):
            raise ValueError("Use letters, numbers, dots, underscores, or hyphens.")

    def _create_structure(self) -> None:
        test_name = self.test_name_input.text().strip()
        try:
            self._validate_name(test_name)
        except ValueError as exc:
            QMessageBox.warning(self, "Check your input", str(exc))
            return

        destination = TEST_BUILD_PATH / test_name
        if destination.exists():
            QMessageBox.warning(
                self,
                "Already exists",
                f"The folder '{destination}' already exists.",
            )
            return

        created_paths: list[Path] = []
        try:
            destination.mkdir(parents=True, exist_ok=False)
            created_paths.append(destination)
            for sub in SUBDIRECTORIES:
                path = destination / sub
                path.mkdir(parents=True, exist_ok=True)
                created_paths.append(path)
        except OSError as exc:
            QMessageBox.critical(
                self,
                "Creation failed",
                f"Could not create the folder structure:\n{exc}",
            )
            return

        lines = [
            f"Created folders under {destination}:",
            *(str(path.relative_to(PROJECT_ROOT)) for path in created_paths),
        ]
        self.output_view.setPlainText("\n".join(lines))
