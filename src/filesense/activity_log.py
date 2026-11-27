"""Recent activity history for FileSense."""

from __future__ import annotations

import json
import os
from datetime import datetime

from PySide6.QtCore import Qt
if os.environ.get("FILESENSE_QML_RUNTIME") == "1":
    class _WidgetsUiOnly:
        pass

    QDialog = QHeaderView = QTextBrowser = QVBoxLayout = PushButton = SubtitleLabel = _WidgetsUiOnly
else:
    from PySide6.QtWidgets import QDialog, QHeaderView, QTextBrowser, QVBoxLayout
    from qfluentwidgets import PushButton, SubtitleLabel

from .app_common import make_table, resource_path, set_item


def log_activity(window, action: str, details: str) -> None:
    try:
        entries = json.loads(window.settings.value("recent_activity", "[]"))
        if not isinstance(entries, list):
            entries = []
    except (TypeError, ValueError):
        entries = []
    entries.insert(0, {
        "time": datetime.now().astimezone().isoformat(timespec="seconds"),
        "action": action,
        "details": details,
    })
    window.settings.setValue("recent_activity", json.dumps(entries[:30], ensure_ascii=False))


def show_activity_log(window) -> None:
    dialog = QDialog(window)
    dialog.setWindowTitle("Recent activity")
    dialog.setMinimumSize(760, 380)
    dialog.resize(1040, 500)
    layout = QVBoxLayout(dialog)
    layout.setContentsMargins(16, 14, 16, 14)
    layout.setSpacing(10)
    layout.addWidget(SubtitleLabel("Last 30 completed actions", dialog))
    table = make_table(["Date and time", "Action", "What was performed"], dialog)
    table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
    table.setColumnWidth(0, 175)
    table.setColumnWidth(1, 210)
    table.setColumnWidth(2, 600)
    table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    table.setWordWrap(False)
    table.setTextElideMode(Qt.TextElideMode.ElideNone)
    try:
        entries = json.loads(window.settings.value("recent_activity", "[]"))
        if not isinstance(entries, list):
            entries = []
    except (TypeError, ValueError):
        entries = []
    if entries:
        table.setRowCount(min(30, len(entries)))
        for row, entry in enumerate(entries[:30]):
            try:
                timestamp = datetime.fromisoformat(entry.get("time", "")).astimezone().strftime("%m-%d-%Y %H:%M:%S")
            except (TypeError, ValueError):
                timestamp = "Unknown time"
            action = str(entry.get("action", "Action"))
            details = str(entry.get("details", ""))
            for column, value in enumerate((timestamp, action, details)):
                set_item(table, row, column, value)
                table.item(row, column).setToolTip(value)
    else:
        table.setRowCount(1)
        set_item(table, 0, 0, "—")
        set_item(table, 0, 1, "No activity yet")
        set_item(table, 0, 2, "Completed file operations will appear here.")
    layout.addWidget(table, 1)
    close = PushButton("Close", dialog)
    close.clicked.connect(dialog.accept)
    layout.addWidget(close, alignment=Qt.AlignmentFlag.AlignRight)
    dialog.exec()


def show_readme(window) -> None:
    dialog = QDialog(window)
    dialog.setWindowTitle("FileSense — Read me")
    dialog.setMinimumSize(680, 480)
    dialog.resize(900, 680)
    layout = QVBoxLayout(dialog)
    layout.setContentsMargins(16, 14, 16, 14)

    reader = QTextBrowser(dialog)
    reader.setOpenExternalLinks(True)
    try:
        markdown = resource_path("README.md").read_text(encoding="utf-8")
    except OSError:
        markdown = "# FileSense\n\nThe README file could not be opened."
    reader.setMarkdown(markdown)
    layout.addWidget(reader, 1)

    close = PushButton("Close", dialog)
    close.clicked.connect(dialog.accept)
    layout.addWidget(close, alignment=Qt.AlignmentFlag.AlignRight)
    dialog.exec()
