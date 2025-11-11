"""PyQt6 widgets for managing timestamped Bubblexan test folders."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Tuple

import config
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

_VALID_NAME = re.compile(r"^[A-Za-z0-9_-]+$")
_SUBDIRECTORIES = [
    Path("inputs"),
    Path("inputs/scans"),
    Path("bubble_sheets"),
    Path("tests"),
    Path("scanned_images"),
    Path("results"),
    Path("grades"),
    Path("miss_analysis"),
    Path("adjustments"),
]


class TestManagerGui(QWidget):
    """Tab that creates and selects test folders with timestamped names."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        config.validate_cli_environment()
        self._existing_titles: set[str] = set()
        self._init_ui()
        self._load_existing_tests()

    def _init_ui(self) -> None:
        font = QFont("Arial", 12)
        self.setFont(font)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 10, 10, 10)

        content_widget = QWidget(self)
        content_widget.setMaximumWidth(520)
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)

        form_layout = QFormLayout()
        form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        form_layout.setFormAlignment(Qt.AlignmentFlag.AlignTop)

        self.test_name_input = QLineEdit()
        self.test_name_input.setPlaceholderText("exam1")
        self.test_name_input.setToolTip("Enter a name for your test")
        form_layout.addRow("Test Name:", self.test_name_input)

        self.test_selector = QComboBox()
        self.test_selector.setToolTip("Select a test you have already created")
        self.test_selector.currentIndexChanged.connect(self._handle_selection)
        form_layout.addRow("Existing Tests:", self.test_selector)

        self.create_button = QPushButton("Create Test Folder")
        self.create_button.setToolTip("Create a new timestamped test folder with all required subfolders")
        self.create_button.setFixedWidth(220)
        self.create_button.clicked.connect(self._handle_create)

        content_layout.addLayout(form_layout)
        content_layout.addWidget(
            self.create_button,
            alignment=Qt.AlignmentFlag.AlignLeft,
        )

        main_layout.addWidget(
            content_widget,
            alignment=Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft,
        )

        output_label = QLabel("Status")
        output_label.setContentsMargins(0, 10, 0, 0)
        main_layout.addWidget(output_label, alignment=Qt.AlignmentFlag.AlignLeft)

        output_container = QWidget(self)
        output_layout = QVBoxLayout(output_container)
        output_layout.setContentsMargins(0, 0, 0, 0)
        output_container.setMinimumWidth(720)
        output_container.setMaximumWidth(860)

        self.output_view = QTextEdit()
        mono = QFont("Courier New", 11)
        self.output_view.setFont(mono)
        self.output_view.setReadOnly(True)
        self.output_view.setMinimumHeight(220)
        self.output_view.setToolTip("Status messages for folder creation and selection")
        output_layout.addWidget(self.output_view)

        main_layout.addWidget(
            output_container,
            alignment=Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft,
        )

        main_layout.addStretch()

    def _handle_create(self) -> None:
        requested_name = self.test_name_input.text().strip()
        try:
            folder_name, folder_path = self._create_test_folder(requested_name)
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid Test Name", str(exc))
            return
        except OSError as exc:  # noqa: PERF203
            QMessageBox.critical(self, "Folder Error", str(exc))
            return

        self._load_existing_tests()
        index = self.test_selector.findData(folder_name)
        if index != -1:
            self.test_selector.setCurrentIndex(index)

        config.ACTIVE_TEST_NAME = folder_name
        self.output_view.append(f"Test folder created: {folder_path}")
        self.test_name_input.clear()

    def _handle_selection(self, index: int) -> None:
        folder_name = self.test_selector.itemData(index)
        if not folder_name:
            return

        folder_path = config.TEST_BUILD_PATH / folder_name
        if not folder_path.exists():
            QMessageBox.warning(
                self,
                "Missing Folder",
                f"The selected folder '{folder_path}' no longer exists.",
            )
            self._load_existing_tests()
            return

        config.ACTIVE_TEST_NAME = folder_name
        self.output_view.append(f"Selected test: {folder_path}")

    def _create_test_folder(self, raw_name: str) -> Tuple[str, Path]:
        if not raw_name:
            raise ValueError("Test name cannot be empty.")
        if not _VALID_NAME.fullmatch(raw_name):
            raise ValueError(
                f"Test name '{raw_name}' is invalid. Use letters, numbers, underscores, or hyphens."
            )

        if raw_name in self._existing_titles:
            raise ValueError(
                f"A test named '{raw_name}' already exists. Choose a unique name."
            )

        timestamp = datetime.now().strftime("%Y%m%d_%H%M")
        folder_name = f"{raw_name}_{timestamp}"
        folder_path = config.TEST_BUILD_PATH / folder_name
        if folder_path.exists():
            raise OSError(
                f"Folder '{folder_path}' already exists. Wait a minute and try again for a new timestamp."
            )

        folder_path.mkdir(parents=True, exist_ok=False)
        for subdir in _SUBDIRECTORIES:
            (folder_path / subdir).mkdir(parents=True, exist_ok=True)

        return folder_name, folder_path

    def _load_existing_tests(self) -> None:
        self._existing_titles.clear()

        self.test_selector.blockSignals(True)
        self.test_selector.clear()
        self.test_selector.addItem("Select a test…", None)

        if not config.TEST_BUILD_PATH.exists():
            config.TEST_BUILD_PATH.mkdir(parents=True, exist_ok=True)

        for folder in sorted(config.TEST_BUILD_PATH.iterdir()):
            if not folder.is_dir():
                continue
            title, timestamp = self._extract_title_and_timestamp(folder.name)
            if not title or not timestamp:
                continue
            if title in self._existing_titles:
                # Skip duplicates; enforce uniqueness on creation time.
                continue
            self._existing_titles.add(title)
            self.test_selector.addItem(title, folder.name)

        self.test_selector.blockSignals(False)

    @staticmethod
    def _extract_title_and_timestamp(folder_name: str) -> Tuple[str | None, str | None]:
        parts = folder_name.rsplit("_", 2)
        if len(parts) != 3:
            return None, None
        title, date_part, time_part = parts
        if not title or not date_part or not time_part:
            return None, None
        timestamp = f"{date_part}_{time_part}"
        if not title:
            return None, None
        return title, timestamp
