"""File name, type, size, and date search for FileSense."""

from __future__ import annotations

import os
import re
import stat
import subprocess
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, QDate, QStorageInfo, QThread, Signal, QUrl
from PySide6.QtGui import QDesktopServices
if os.environ.get("FILESENSE_QML_RUNTIME") == "1":
    class _WidgetsUiOnly:
        pass

    (QAbstractItemView, QFileDialog, QHBoxLayout, QListWidget, QListWidgetItem,
     QMessageBox, QVBoxLayout, QWidget, BodyLabel, CaptionLabel, CardWidget,
     FluentIcon, LineEdit, PrimaryPushButton, PushButton, StrongBodyLabel,
     SubtitleLabel) = (_WidgetsUiOnly,) * 17
else:
    from PySide6.QtWidgets import (
        QAbstractItemView, QFileDialog, QHBoxLayout, QListWidget, QListWidgetItem,
        QMessageBox, QVBoxLayout, QWidget,
    )
    from qfluentwidgets import (
        BodyLabel, CaptionLabel, CardWidget, FluentIcon, LineEdit,
        PrimaryPushButton, PushButton, StrongBodyLabel, SubtitleLabel,
    )

from .app_common import (
    CATEGORIES, CheckBox, QDateEdit, QHeaderView, QProgressBar, QTableWidgetItem, TableWidget,
    TitleLabel, file_type, format_bytes,
)


MAX_RESULTS = 10000
REPARSE_POINT = 0x400


@dataclass(frozen=True)
class SearchCriteria:
    roots: tuple[str, ...]
    exclusions: tuple[str, ...]
    name: str
    extensions: tuple[str, ...]
    categories: tuple[str, ...]
    minimum_bytes: int | None
    maximum_bytes: int | None
    created_start: float | None
    created_end: float | None
    modified_start: float | None
    modified_end: float | None
    include_subfolders: bool = True

    @property
    def has_file_filters(self) -> bool:
        return bool(
            self.extensions or self.categories or self.minimum_bytes is not None
            or self.maximum_bytes is not None or self.created_start is not None
            or self.created_end is not None or self.modified_start is not None
            or self.modified_end is not None
        )


@dataclass
class SearchResult:
    path: str
    is_directory: bool
    size: int
    created: float
    modified: float


def _norm_path(path: str | Path) -> str:
    return os.path.normcase(os.path.abspath(os.path.expanduser(str(path))))


def _is_within(path: str | Path, root: str | Path) -> bool:
    try:
        return os.path.commonpath((_norm_path(path), _norm_path(root))) == _norm_path(root)
    except ValueError:
        return False


def _collapse_roots(paths: tuple[str, ...]) -> list[Path]:
    unique: dict[str, Path] = {}
    for raw in paths:
        path = Path(os.path.abspath(os.path.expanduser(raw)))
        key = _norm_path(path)
        unique.setdefault(key, path)
    ordered = sorted(unique.values(), key=lambda path: (len(_norm_path(path)), _norm_path(path)))
    roots: list[Path] = []
    for path in ordered:
        if not any(_is_within(path, root) for root in roots):
            roots.append(path)
    return roots


def _is_reparse(info: os.stat_result) -> bool:
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & REPARSE_POINT)


def _normalize_extensions(raw: str) -> tuple[str, ...]:
    values = []
    for value in re.split(r"[,;\s]+", raw.strip().casefold()):
        value = value.strip()
        if not value:
            continue
        if not value.startswith("."):
            value = "." + value
        if len(value) > 1:
            values.append(value)
    return tuple(dict.fromkeys(values))


def _matches(path: Path, info: os.stat_result, criteria: SearchCriteria, is_directory: bool) -> bool:
    if criteria.name and criteria.name.casefold() not in path.name.casefold():
        return False
    if is_directory:
        return not criteria.has_file_filters

    if criteria.extensions and not any(path.name.casefold().endswith(ext) for ext in criteria.extensions):
        return False
    if criteria.categories and file_type(path) not in criteria.categories:
        return False
    if criteria.minimum_bytes is not None and info.st_size < criteria.minimum_bytes:
        return False
    if criteria.maximum_bytes is not None and info.st_size > criteria.maximum_bytes:
        return False
    if criteria.created_start is not None and info.st_ctime < criteria.created_start:
        return False
    if criteria.created_end is not None and info.st_ctime > criteria.created_end:
        return False
    if criteria.modified_start is not None and info.st_mtime < criteria.modified_start:
        return False
    if criteria.modified_end is not None and info.st_mtime > criteria.modified_end:
        return False
    return True


class FileSearchWorker(QThread):
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, criteria: SearchCriteria, cancel: threading.Event, parent=None):
        super().__init__(parent)
        self.criteria = criteria
        self.cancel = cancel

    def run(self) -> None:
        results: list[SearchResult] = []
        issues: list[str] = []
        scanned_files = 0
        scanned_folders = 0
        truncated = False
        cancelled = False
        visited: set[str] = set()
        excluded = tuple(_norm_path(path) for path in self.criteria.exclusions)
        try:
            for root in _collapse_roots(self.criteria.roots):
                if self.cancel.is_set():
                    cancelled = True
                    break
                try:
                    root_info = os.lstat(root)
                except OSError as error:
                    issues.append(f"{root}: {error}")
                    continue
                if not stat.S_ISDIR(root_info.st_mode) or _is_reparse(root_info):
                    issues.append(f"{root}: skipped because it is not a regular folder or drive.")
                    continue

                # A selected drive or volume root always means a full recursive scan.
                include_nested = self.criteria.include_subfolders or root == Path(root.anchor)
                pending = [root]
                while pending:
                    if self.cancel.is_set():
                        cancelled = True
                        break
                    directory = pending.pop()
                    directory_key = _norm_path(directory)
                    if directory_key in visited or any(_is_within(directory_key, blocked) for blocked in excluded):
                        continue
                    visited.add(directory_key)
                    try:
                        with os.scandir(directory) as entries:
                            children = list(entries)
                    except OSError as error:
                        if len(issues) < 1000:
                            issues.append(f"{directory}: {error}")
                        continue
                    scanned_folders += 1
                    for entry in children:
                        if self.cancel.is_set():
                            cancelled = True
                            break
                        path = Path(entry.path)
                        key = _norm_path(path)
                        if any(_is_within(key, blocked) for blocked in excluded):
                            continue
                        try:
                            info = entry.stat(follow_symlinks=False)
                        except OSError as error:
                            if len(issues) < 1000:
                                issues.append(f"{path}: {error}")
                            continue
                        if _is_reparse(info):
                            continue
                        is_directory = stat.S_ISDIR(info.st_mode)
                        if is_directory:
                            if include_nested and _matches(path, info, self.criteria, True):
                                results.append(SearchResult(str(path), True, 0, info.st_ctime, info.st_mtime))
                            if include_nested:
                                pending.append(path)
                        elif stat.S_ISREG(info.st_mode):
                            scanned_files += 1
                            if _matches(path, info, self.criteria, False):
                                results.append(SearchResult(str(path), False, info.st_size, info.st_ctime, info.st_mtime))
                        if len(results) >= MAX_RESULTS:
                            truncated = True
                            break
                    if truncated or cancelled:
                        break
                if truncated or cancelled:
                    break

            self.completed.emit({
                "results": results,
                "issues": issues,
                "scanned_files": scanned_files,
                "scanned_folders": scanned_folders,
                "truncated": truncated,
                "cancelled": cancelled,
                "criteria": self.criteria,
            })
        except Exception as error:
            self.failed.emit(str(error))


class FileSearchInterface(QWidget):
    LOCATION_KIND = Qt.ItemDataRole.UserRole + 1
    LOCATION_PATH = Qt.ItemDataRole.UserRole + 2

    def __init__(self, parent_window: QWidget):
        super().__init__()
        self.parent_window = parent_window
        self.worker: FileSearchWorker | None = None
        self.cancel_event: threading.Event | None = None
        self.results: list[SearchResult] = []
        self._build()
        self._load_saved_locations()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(6)
        layout.addWidget(TitleLabel("File Search & Finder"))
        layout.addWidget(CaptionLabel("Find files and folders by name, type, size, or date."))

        search_card = CardWidget(self)
        search_layout = QHBoxLayout(search_card)
        search_layout.setContentsMargins(12, 8, 12, 8)
        search_layout.setSpacing(10)
        search_layout.addWidget(StrongBodyLabel("Search by name"))
        self.name_input = LineEdit(search_card)
        self.name_input.setPlaceholderText("Enter a full or partial filename, e.g. report.pdf, invoice, or presentation")
        search_layout.addWidget(self.name_input, 1)
        layout.addWidget(search_card)

        location_row = QHBoxLayout()
        location_row.setSpacing(10)
        location_card = CardWidget(self)
        location_layout = QVBoxLayout(location_card)
        location_layout.setContentsMargins(10, 7, 10, 7)
        location_layout.setSpacing(5)
        location_heading = QHBoxLayout()
        location_heading.addWidget(StrongBodyLabel("Search locations"))
        location_heading.addStretch(1)
        browse = PushButton(FluentIcon.FOLDER_ADD, "Browse…", location_card)
        browse.setFixedHeight(30)
        browse.clicked.connect(self.add_location)
        remove = PushButton(FluentIcon.DELETE, "Remove", location_card)
        remove.setFixedHeight(30)
        remove.clicked.connect(self.remove_locations)
        location_heading.addWidget(browse)
        location_heading.addWidget(remove)
        location_layout.addLayout(location_heading)
        self.location_list = QListWidget(location_card)
        self.location_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.location_list.setMaximumHeight(82)
        location_layout.addWidget(self.location_list)
        location_row.addWidget(location_card, 1)

        exclude_card = CardWidget(self)
        exclude_layout = QVBoxLayout(exclude_card)
        exclude_layout.setContentsMargins(10, 7, 10, 7)
        exclude_layout.setSpacing(5)
        exclude_heading = QHBoxLayout()
        exclude_heading.addWidget(StrongBodyLabel("Exclude folders (optional)"))
        exclude_heading.addStretch(1)
        add_excluded = PushButton(FluentIcon.FOLDER_ADD, "Add…", exclude_card)
        add_excluded.setFixedHeight(30)
        add_excluded.clicked.connect(self.add_exclusion)
        remove_excluded = PushButton(FluentIcon.DELETE, "Remove", exclude_card)
        remove_excluded.setFixedHeight(30)
        remove_excluded.clicked.connect(self.remove_exclusions)
        exclude_heading.addWidget(add_excluded)
        exclude_heading.addWidget(remove_excluded)
        exclude_layout.addLayout(exclude_heading)
        self.exclude_list = QListWidget(exclude_card)
        self.exclude_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.exclude_list.setMaximumHeight(82)
        exclude_layout.addWidget(self.exclude_list)
        location_row.addWidget(exclude_card, 1)
        layout.addLayout(location_row)

        self.advanced_toggle = CheckBox("Show advanced filters", self)
        self.advanced_toggle.setChecked(False)
        self.advanced_toggle.toggled.connect(self._toggle_advanced)
        layout.addWidget(self.advanced_toggle)
        self.advanced_card = CardWidget(self)
        advanced_layout = QHBoxLayout(self.advanced_card)
        advanced_layout.setContentsMargins(12, 9, 12, 9)
        advanced_layout.setSpacing(12)
        advanced_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        type_box = QVBoxLayout()
        type_box.setAlignment(Qt.AlignmentFlag.AlignTop)
        type_box.setSpacing(5)
        type_box.addWidget(StrongBodyLabel("File type (choose any)"))
        self.category_list = QListWidget(self.advanced_card)
        self.category_list.setFixedHeight(100)
        self.category_list.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        for category in (*CATEGORIES.keys(), "Other"):
            item = QListWidgetItem(category, self.category_list)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
        type_box.addWidget(self.category_list)
        advanced_layout.addLayout(type_box, 1)

        filters_box = QVBoxLayout()
        filters_box.setSpacing(5)
        extension_row = QHBoxLayout()
        extension_row.addWidget(StrongBodyLabel("Extensions"))
        self.extensions_input = LineEdit(self.advanced_card)
        self.extensions_input.setPlaceholderText(".jpg, .jpeg, .png")
        extension_row.addWidget(self.extensions_input, 1)
        filters_box.addLayout(extension_row)

        size_row = QHBoxLayout()
        size_row.addWidget(CaptionLabel("Size (MB)"))
        self.minimum_size = LineEdit(self.advanced_card)
        self.minimum_size.setPlaceholderText("Minimum MB")
        self.maximum_size = LineEdit(self.advanced_card)
        self.maximum_size.setPlaceholderText("Maximum MB")
        size_row.addWidget(self.minimum_size)
        size_row.addWidget(self.maximum_size)
        filters_box.addLayout(size_row)

        self.created_enabled = CheckBox("Created between", self.advanced_card)
        self.created_start = self._date_picker(self.advanced_card)
        self.created_end = self._date_picker(self.advanced_card)
        created_row = QHBoxLayout()
        created_row.addWidget(self.created_enabled)
        created_row.addWidget(self.created_start, 1)
        created_row.addWidget(BodyLabel("to"))
        created_row.addWidget(self.created_end, 1)
        filters_box.addLayout(created_row)
        self.modified_enabled = CheckBox("Modified between", self.advanced_card)
        self.modified_start = self._date_picker(self.advanced_card)
        self.modified_end = self._date_picker(self.advanced_card)
        modified_row = QHBoxLayout()
        modified_row.addWidget(self.modified_enabled)
        modified_row.addWidget(self.modified_start, 1)
        modified_row.addWidget(BodyLabel("to"))
        modified_row.addWidget(self.modified_end, 1)
        filters_box.addLayout(modified_row)
        self.created_start.setEnabled(False)
        self.created_end.setEnabled(False)
        self.modified_start.setEnabled(False)
        self.modified_end.setEnabled(False)
        self.created_enabled.toggled.connect(self.created_start.setEnabled)
        self.created_enabled.toggled.connect(self.created_end.setEnabled)
        self.modified_enabled.toggled.connect(self.modified_start.setEnabled)
        self.modified_enabled.toggled.connect(self.modified_end.setEnabled)
        advanced_layout.addLayout(filters_box, 2)
        self.advanced_card.hide()
        layout.addWidget(self.advanced_card)

        actions = QHBoxLayout()
        self.search_button = PrimaryPushButton(FluentIcon.SEARCH, "Search", self)
        self.search_button.setFixedWidth(100)
        self.search_button.setFixedHeight(30)
        self.search_button.clicked.connect(self.start_search)
        actions.addWidget(self.search_button)
        self.cancel_button = PushButton("Cancel scan", self)
        self.cancel_button.setFixedHeight(30)
        self.cancel_button.clicked.connect(self.cancel_search)
        self.cancel_button.hide()
        actions.addWidget(self.cancel_button)
        self.open_location_button = PushButton(FluentIcon.FOLDER, "Open location", self)
        self.open_location_button.setFixedHeight(30)
        self.open_location_button.clicked.connect(self.open_selected_location)
        actions.addWidget(self.open_location_button)
        actions.addStretch(1)
        layout.addLayout(actions)

        self.progress = QProgressBar(self)
        self.progress.setRange(0, 0)
        self.progress.hide()
        layout.addWidget(self.progress)
        self.status = CaptionLabel("Select one or more drives or folders to search.", self)
        layout.addWidget(self.status)

        self.table = TableWidget(self)
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["Name", "Type", "Size", "Modified", "Location"])
        self.table.setSelectionBehavior(TableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(TableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(False)
        self.table.setMinimumHeight(240)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.table.doubleClicked.connect(self.open_selected_location)
        layout.addWidget(self.table, 1)

    @staticmethod
    def _date_picker(parent: QWidget) -> QDateEdit:
        picker = QDateEdit(parent)
        picker.setCalendarPopup(True)
        picker.setDisplayFormat("MM-dd-yyyy")
        picker.setDate(QDate.currentDate())
        picker.setFixedHeight(30)
        return picker

    @staticmethod
    def _date_row(start: QDateEdit, end: QDateEdit) -> QHBoxLayout:
        row = QHBoxLayout()
        row.addWidget(start)
        row.addWidget(BodyLabel("to"))
        row.addWidget(end)
        return row

    def _toggle_advanced(self, visible: bool) -> None:
        self.advanced_card.setVisible(visible)

    def _load_saved_locations(self) -> None:
        saved = self.parent_window.settings.value("file_search_locations", [])
        if isinstance(saved, str):
            saved = [saved]
        saved_set = {_norm_path(path) for path in saved or []}
        drives: set[str] = set()
        for storage in QStorageInfo.mountedVolumes():
            root = storage.rootPath()
            if storage.isReady() and root and os.path.isdir(root):
                path = Path(root)
                key = _norm_path(path)
                drives.add(key)
                label = f"{path} — {storage.name()}" if storage.name() else str(path)
                self._add_location_item(path, label, "drive", key in saved_set)
        for raw in saved or []:
            path = Path(str(raw))
            if _norm_path(path) not in drives and path.is_dir():
                self._add_location_item(path, str(path), "folder", True)
        excluded = self.parent_window.settings.value("file_search_exclusions", [])
        if isinstance(excluded, str):
            excluded = [excluded]
        for raw in excluded or []:
            path = Path(str(raw))
            if path.is_dir():
                self.exclude_list.addItem(str(path))

    def _add_location_item(self, path: Path, label: str, kind: str, checked: bool) -> None:
        item = QListWidgetItem(label, self.location_list)
        item.setData(self.LOCATION_KIND, kind)
        item.setData(self.LOCATION_PATH, str(path))
        item.setToolTip(str(path))
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)

    def add_location(self) -> None:
        selected = QFileDialog.getExistingDirectory(self, "Select a folder to search", str(Path.home()))
        if not selected:
            return
        key = _norm_path(selected)
        for index in range(self.location_list.count()):
            item = self.location_list.item(index)
            if _norm_path(item.data(self.LOCATION_PATH)) == key:
                item.setCheckState(Qt.CheckState.Checked)
                return
        self._add_location_item(Path(selected), selected, "folder", True)

    def remove_locations(self) -> None:
        for item in self.location_list.selectedItems():
            if item.data(self.LOCATION_KIND) == "folder":
                self.location_list.takeItem(self.location_list.row(item))
            else:
                item.setCheckState(Qt.CheckState.Unchecked)

    def add_exclusion(self) -> None:
        selected = QFileDialog.getExistingDirectory(self, "Select a folder to exclude", str(Path.home()))
        if selected and not any(_norm_path(self.exclude_list.item(i).text()) == _norm_path(selected)
                                for i in range(self.exclude_list.count())):
            self.exclude_list.addItem(selected)

    def remove_exclusions(self) -> None:
        for item in self.exclude_list.selectedItems():
            self.exclude_list.takeItem(self.exclude_list.row(item))

    def _checked_paths(self, widget: QListWidget, role: int) -> tuple[str, ...]:
        values = []
        for index in range(widget.count()):
            item = widget.item(index)
            if item.checkState() == Qt.CheckState.Checked:
                values.append(str(item.data(role)))
        return tuple(values)

    def _criteria(self) -> SearchCriteria:
        roots = self._checked_paths(self.location_list, self.LOCATION_PATH)
        if not roots:
            raise ValueError("Select at least one drive or folder to search.")
        name = self.name_input.text().strip()
        extensions = _normalize_extensions(self.extensions_input.text())
        categories = tuple(
            self.category_list.item(index).text()
            for index in range(self.category_list.count())
            if self.category_list.item(index).checkState() == Qt.CheckState.Checked
        )
        minimum = self._size_value(self.minimum_size.text(), "minimum")
        maximum = self._size_value(self.maximum_size.text(), "maximum")
        if minimum is not None and maximum is not None and minimum > maximum:
            raise ValueError("Minimum size must not exceed maximum size.")
        created_start, created_end = self._date_range(self.created_enabled, self.created_start, self.created_end)
        modified_start, modified_end = self._date_range(self.modified_enabled, self.modified_start, self.modified_end)
        if not name and not extensions and not categories and minimum is None and maximum is None and created_start is None and modified_start is None:
            raise ValueError("Enter a name or choose at least one search filter.")
        exclusions = tuple(self.exclude_list.item(i).text() for i in range(self.exclude_list.count()))
        return SearchCriteria(roots, exclusions, name, extensions, categories,
                              minimum, maximum, created_start, created_end, modified_start, modified_end)

    @staticmethod
    def _size_value(text: str, label: str) -> int | None:
        value = text.strip()
        if not value:
            return None
        try:
            number = float(value)
        except ValueError as error:
            raise ValueError(f"The {label} size must be a number of MB.") from error
        if number < 0:
            raise ValueError(f"The {label} size cannot be negative.")
        return int(number * 1024 * 1024)

    @staticmethod
    def _date_range(enabled: CheckBox, start: QDateEdit, end: QDateEdit) -> tuple[float | None, float | None]:
        if not enabled.isChecked():
            return None, None
        first = datetime.strptime(start.date().toString("yyyy-MM-dd"), "%Y-%m-%d").date()
        last = datetime.strptime(end.date().toString("yyyy-MM-dd"), "%Y-%m-%d").date()
        if last < first:
            raise ValueError("The end date must be the same as or later than the start date.")
        return datetime.combine(first, datetime.min.time()).timestamp(), datetime.combine(last, datetime.max.time()).timestamp()

    def start_search(self) -> None:
        self._start_search()

    def _start_search(self) -> None:
        if self.worker and self.worker.isRunning():
            return
        try:
            criteria = self._criteria()
        except ValueError as error:
            QMessageBox.information(self, "Complete search options", str(error))
            return
        self.parent_window.settings.setValue("file_search_locations", list(criteria.roots))
        self.parent_window.settings.setValue("file_search_exclusions", list(criteria.exclusions))
        self.table.setRowCount(0)
        self.results = []
        self.search_button.setEnabled(False)
        self.cancel_button.show()
        self.progress.show()
        self.status.setText("Searching selected locations…")
        self.cancel_event = threading.Event()
        self.worker = FileSearchWorker(criteria, self.cancel_event, self)
        self.worker.completed.connect(self._search_completed)
        self.worker.failed.connect(self._search_failed)
        self.worker.start()

    def cancel_search(self) -> None:
        if self.cancel_event:
            self.cancel_event.set()
            self.status.setText("Stopping the search…")

    def _search_completed(self, result: dict[str, Any]) -> None:
        criteria: SearchCriteria = result["criteria"]
        self.progress.hide()
        self.cancel_button.hide()
        self.search_button.setEnabled(True)
        self.results = result["results"]
        self.table.setRowCount(len(self.results))
        for row, match in enumerate(self.results):
            path = Path(match.path)
            values = [
                path.name,
                "Folder" if match.is_directory else file_type(path),
                "—" if match.is_directory else format_bytes(match.size),
                datetime.fromtimestamp(match.modified).strftime("%m-%d-%Y %H:%M"),
                str(path.parent),
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setToolTip(match.path)
                if column == 0:
                    item.setData(Qt.ItemDataRole.UserRole, match.path)
                self.table.setItem(row, column, item)
        issues = result["issues"]
        message = (
            f"Found {len(self.results):,} result(s) · scanned {result['scanned_files']:,} files "
            f"and {result['scanned_folders']:,} folders · {len(issues):,} inaccessible or skipped location(s)."
        )
        if result["truncated"]:
            message += f" Showing the first {MAX_RESULTS:,} matches."
        if result["cancelled"]:
            message += " Search cancelled."
        self.status.setText(message)
        summary = (
            f"Name: {criteria.name or 'any'}; extensions: {', '.join(criteria.extensions) or 'any'}; "
            f"categories: {', '.join(criteria.categories) or 'any'}; roots: {', '.join(criteria.roots)}; "
            f"results: {len(self.results)}; scanned files: {result['scanned_files']}; "
            f"skipped/inaccessible: {len(issues)}; cancelled: {result['cancelled']}."
        )
        self.parent_window.log_activity("File search", summary)
        if issues:
            QMessageBox.information(self, "Some locations were skipped", "Some folders could not be read:\n\n" + "\n".join(issues[:10]))

    def _search_failed(self, message: str) -> None:
        self.progress.hide()
        self.cancel_button.hide()
        self.search_button.setEnabled(True)
        self.status.setText("Search failed.")
        QMessageBox.critical(self, "Search failed", message)

    def open_selected_location(self, *_args) -> None:
        row = self.table.currentRow()
        if row < 0:
            return
        item = self.table.item(row, 0)
        if item is None:
            return
        path = Path(item.data(Qt.ItemDataRole.UserRole))
        if os.name == "nt":
            subprocess.Popen(["explorer.exe", f"/select,{path}"])
        else:
            location = path if path.is_dir() else path.parent
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(location)))
