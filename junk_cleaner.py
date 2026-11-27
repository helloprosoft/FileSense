"""Category-based, reviewable cleanup for FileSense."""

from __future__ import annotations

import base64
import ctypes
import fnmatch
import os
import shutil
import stat
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, QThread, Signal, QUrl
from PySide6.QtGui import QDesktopServices
if os.environ.get("FILESENSE_QML_RUNTIME") == "1":
    class _WidgetsUiOnly:
        pass

    (QAbstractItemView, QHBoxLayout, QHeaderView, QMessageBox, QProgressBar,
     QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget, BodyLabel, CaptionLabel,
     CardWidget, FluentIcon, PrimaryPushButton, PushButton, StrongBodyLabel,
     SubtitleLabel, TitleLabel) = (_WidgetsUiOnly,) * 18
else:
    from PySide6.QtWidgets import (
        QAbstractItemView, QHBoxLayout, QHeaderView, QMessageBox, QProgressBar,
        QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
    )
    from qfluentwidgets import (
        BodyLabel, CaptionLabel, CardWidget, FluentIcon, PrimaryPushButton,
        PushButton, StrongBodyLabel, SubtitleLabel, TitleLabel,
    )

from app_common import format_bytes, send_to_recycle_bin


MAX_ITEMS_PER_CATEGORY = 5000
MAX_ISSUES_PER_CATEGORY = 300
MAX_ENTRIES_PER_ROOT = 100000
REPARSE_POINT = 0x400
PROTECTED_NAMES = {
    "cookies", "login data", "web data", "passwords", "downloads",
    "history", "bookmarks", "favorites",
}


@dataclass(frozen=True)
class CleanupCategory:
    key: str
    label: str
    roots: tuple[Path, ...] = ()
    patterns: tuple[str, ...] = ("*",)
    age_days: int | None = None
    mode: str = "files"
    recursive: bool = True
    description: str = ""
    group: str = "Other system items"
    recommended: bool = False


@dataclass
class CleanupCandidate:
    category: str
    path: str = ""
    root: str = ""
    size: int = 0
    modified_ns: int = 0
    inode: int = 0
    is_directory: bool = False
    item_count: int = 1
    kind: str = "file"


@dataclass
class CleanupIssue:
    category: str
    path: str
    reason: str


def _env_path(name: str, fallback: str = "") -> Path:
    value = os.environ.get(name, fallback)
    return Path(os.path.expandvars(value)) if value else Path()


def _category_specs() -> list[CleanupCategory]:
    local = _env_path("LOCALAPPDATA", str(Path.home() / "AppData/Local"))
    roaming = _env_path("APPDATA", str(Path.home() / "AppData/Roaming"))
    program = _env_path("PROGRAMDATA", "C:/ProgramData")
    windows = _env_path("WINDIR", "C:/Windows")
    temp = _env_path("TEMP", tempfile_path())

    browser_roots: dict[str, list[Path]] = {
        "Chrome": [], "Edge": [], "Firefox": [],
    }
    for browser, pattern in (
        ("Chrome", local / "Google/Chrome/User Data/*/Cache/Cache_Data"),
        ("Edge", local / "Microsoft/Edge/User Data/*/Cache/Cache_Data"),
        ("Firefox", local / "Mozilla/Firefox/Profiles/*/cache2/entries"),
    ):
        try:
            browser_roots[browser].extend(Path(path) for path in glob_paths(pattern))
        except OSError:
            continue

    app_cache_roots = {
        "NVIDIA": tuple(path for path in (local / "NVIDIA/DXCache", local / "NVIDIA/GLCache") if path.exists()),
        "Python pip": (local / "pip/Cache",) if (local / "pip/Cache").exists() else (),
    }

    ordinary_roots = (
        temp,
        windows / "Temp",
        local / "Microsoft/Windows/Explorer",
        local / "D3DSCache",
        program / "Microsoft/Windows/WER/ReportQueue",
        program / "Microsoft/Windows/WER/ReportArchive",
        local / "Microsoft/Windows/WER/ReportQueue",
        local / "Microsoft/Windows/WER/ReportArchive",
        local / "ProSoft/FileSense/Cache",
        local / "ProSoft/FileSense/Logs",
        local / "CrashDumps",
        *(path for roots in browser_roots.values() for path in roots),
        *(path for roots in app_cache_roots.values() for path in roots),
    )
    roots_for_empty = tuple(dict.fromkeys(path for path in ordinary_roots if path.is_dir()))
    return [
        CleanupCategory(
            "user_temp", "User temporary files", (temp,), age_days=1,
            description="%TEMP% files last modified at least 1 day ago.",
            group="Recommended items · System items", recommended=True,
        ),
        CleanupCategory(
            "windows_temp", "Windows temporary files", (windows / "Temp",), age_days=7,
            description="Windows Temp files last modified at least 7 days ago. Access-limited files are skipped.",
            group="Recommended items · System items", recommended=True,
        ),
        CleanupCategory(
            "recycle_bin", "Recycle Bin", mode="recycle_bin",
            description="Emptying permanently removes these deleted files; this is a separate confirmed action.",
            group="Other system items",
        ),
        CleanupCategory(
            "thumbnail_cache", "Thumbnail cache", (local / "Microsoft/Windows/Explorer",),
            patterns=("thumbcache*.db",), recursive=False,
            description="Explorer thumbnail database files. Windows may keep some files locked.",
            group="Recommended items · System items", recommended=True,
        ),
        CleanupCategory(
            "directx_cache", "DirectX shader cache", (local / "D3DSCache",),
            description="Files in the user DirectX shader cache. Windows and applications can recreate them.",
            group="Other system items",
        ),
        CleanupCategory(
            "wer_reports", "Windows error reports", (
                program / "Microsoft/Windows/WER/ReportQueue",
                program / "Microsoft/Windows/WER/ReportArchive",
                local / "Microsoft/Windows/WER/ReportQueue",
                local / "Microsoft/Windows/WER/ReportArchive",
            ), age_days=30,
            description="Windows Error Reporting files last modified at least 30 days ago.",
            group="Recommended items · System items", recommended=True,
        ),
        CleanupCategory(
            "application_cache", "Application cache", (local / "ProSoft/FileSense/Cache",),
            age_days=30,
            description="Only FileSense's own cache folder is scanned; other application caches are left untouched.",
            group="Other application items",
        ),
        *[
            CleanupCategory(
                f"{browser.casefold()}_cache", f"{browser} Cache", tuple(roots), age_days=7,
                description=f"{browser} cache files last modified at least 7 days ago. Cookies, passwords, history and downloads are excluded.",
                group="Recommended items · Application items", recommended=True,
            )
            for browser, roots in browser_roots.items()
            if roots
        ],
        *[
            CleanupCategory(
                f"{app.casefold().replace(' ', '_')}_cache", f"{app} cache", roots, age_days=14,
                description=f"Only the known {app} cache location is scanned. Cache files newer than 14 days are left untouched.",
                group="Other application items",
            )
            for app, roots in app_cache_roots.items()
            if roots
        ],
        CleanupCategory(
            "logs", "Log files", (local / "ProSoft/FileSense/Logs",), patterns=("*.log",),
            age_days=30,
            description="FileSense log files last modified at least 30 days ago. No arbitrary .log files are scanned.",
            group="Other application items",
        ),
        CleanupCategory(
            "crash_dumps", "Crash dumps", (local / "CrashDumps",), patterns=("*.dmp", "*.mdmp"),
            age_days=30,
            description="User crash dumps last modified at least 30 days ago. Windows system dumps are not scanned.",
            group="Other system items",
        ),
        CleanupCategory(
            "windows_minidumps", "Windows minidump files", (windows / "Minidump",),
            patterns=("*.dmp",), age_days=30,
            description="Windows minidumps at least 30 days old. These may be useful for diagnosing system crashes; review before cleaning.",
            group="Other system items",
        ),
        CleanupCategory(
            "prefetch", "Windows Prefetch", (windows / "Prefetch",),
            patterns=("*.pf",), age_days=30,
            description="Prefetch files at least 30 days old. Windows can recreate them; clearing may temporarily slow app starts.",
            group="Other system items",
        ),
        CleanupCategory(
            "update_cleanup", "Update cleanup (Advanced)", mode="windows_settings",
            description="Use Windows Storage settings for Windows Update leftovers; these are not deleted as ordinary files.",
            group="Other system items",
        ),
        CleanupCategory(
            "delivery_cache", "Delivery Optimization cache (Advanced)",
            (program / "Microsoft/Windows/DeliveryOptimization/Cache",),
            mode="delivery_cache",
            description="Reviewed as a Windows-managed cache and cleaned only through Microsoft's Delivery Optimization cmdlet.",
            group="Recommended items · System items", recommended=True,
        ),
        CleanupCategory(
            "empty_folders", "Empty folders", roots_for_empty,
            mode="empty_folders", recursive=True,
            description="Empty folders inside the listed cleanup locations. Folder links and reparse points are skipped.",
            group="Other system items",
        ),
    ]


def tempfile_path() -> str:
    import tempfile
    return tempfile.gettempdir()


def glob_paths(pattern: Path) -> list[str]:
    import glob
    return glob.glob(str(pattern))


def _is_reparse(st: os.stat_result) -> bool:
    return stat.S_ISLNK(st.st_mode) or bool(getattr(st, "st_file_attributes", 0) & REPARSE_POINT)


def _protected_path(path: Path) -> bool:
    return any(part.casefold() in PROTECTED_NAMES for part in path.parts)


def _matches(path: Path, patterns: tuple[str, ...]) -> bool:
    return any(fnmatch.fnmatchcase(path.name.casefold(), pattern.casefold()) for pattern in patterns)


def _append_issue(issues: list[CleanupIssue], category: str, path: Path | str, reason: str) -> None:
    if len(issues) < MAX_ISSUES_PER_CATEGORY:
        issues.append(CleanupIssue(category, str(path), reason))


def _walk_root(
    category: CleanupCategory,
    root: Path,
    now: float,
    issues: list[CleanupIssue],
    collect: bool = True,
) -> tuple[list[CleanupCandidate], int, int]:
    found: list[CleanupCandidate] = []
    total_size = 0
    total_count = 0
    if not root.exists():
        return found, 0, 0
    try:
        root_stat = os.lstat(root)
    except OSError as error:
        _append_issue(issues, category.key, root, f"Could not inspect location: {error}")
        return found, 0, 0
    if not stat.S_ISDIR(root_stat.st_mode) or _is_reparse(root_stat):
        _append_issue(issues, category.key, root, "Skipped: cleanup root is not a regular folder.")
        return found, 0, 0

    cutoff = now - category.age_days * 86400 if category.age_days is not None else None
    pending = [root]
    visited = 0
    limit_hit = False
    while pending:
        if limit_hit:
            break
        directory = pending.pop()
        try:
            with os.scandir(directory) as entries:
                children = list(entries)
        except OSError as error:
            _append_issue(issues, category.key, directory, f"Skipped inaccessible location: {error}")
            continue

        for item in children:
            visited += 1
            if visited % 256 == 0:
                # Let the UI thread run smoothly while a large tree is enumerated.
                time.sleep(0)
            if collect and visited > MAX_ENTRIES_PER_ROOT:
                limit_hit = True
                break
            path = Path(item.path)
            try:
                st = item.stat(follow_symlinks=False)
            except OSError as error:
                _append_issue(issues, category.key, path, f"Skipped inaccessible item: {error}")
                continue
            if _is_reparse(st):
                _append_issue(issues, category.key, path, "Skipped symbolic link or reparse point.")
                continue
            if _protected_path(path):
                _append_issue(issues, category.key, path, "Skipped protected user data.")
                continue
            if stat.S_ISDIR(st.st_mode):
                if category.key == "empty_folders":
                    try:
                        with os.scandir(path) as nested:
                            is_empty = next(nested, None) is None
                    except OSError as error:
                        _append_issue(issues, category.key, path, f"Skipped inaccessible folder: {error}")
                        continue
                    if is_empty:
                        if collect and len(found) >= MAX_ITEMS_PER_CATEGORY:
                            limit_hit = True
                            break
                        total_count += 1
                        if collect:
                            found.append(CleanupCandidate(
                                category.key, str(path), str(root), 0, st.st_mtime_ns,
                                getattr(st, "st_ino", 0), True,
                            ))
                        continue
                if category.recursive:
                    pending.append(path)
                continue
            if not stat.S_ISREG(st.st_mode) or not _matches(path, category.patterns):
                continue
            if cutoff is not None and st.st_mtime > cutoff:
                continue
            if collect and len(found) >= MAX_ITEMS_PER_CATEGORY:
                limit_hit = True
                break
            total_count += 1
            total_size += st.st_size
            if collect:
                found.append(CleanupCandidate(
                    category.key, str(path), str(root), st.st_size, st.st_mtime_ns,
                    getattr(st, "st_ino", 0), False,
                ))
    if limit_hit:
        _append_issue(issues, category.key, root,
                      f"Scan stopped after reaching the safety limit ({MAX_ITEMS_PER_CATEGORY:,} candidates or {MAX_ENTRIES_PER_ROOT:,} entries per location). Rescan later to check for more.")
    return found, total_count, total_size


def _recycle_bin_info() -> tuple[int, int]:
    class SHQUERYRBINFO(ctypes.Structure):
        _fields_ = [("cbSize", ctypes.c_ulong), ("i64Size", ctypes.c_longlong), ("i64NumItems", ctypes.c_longlong)]
    info = SHQUERYRBINFO()
    info.cbSize = ctypes.sizeof(SHQUERYRBINFO)
    shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    query = shell32.SHQueryRecycleBinW
    query.argtypes = [ctypes.c_wchar_p, ctypes.POINTER(SHQUERYRBINFO)]
    query.restype = ctypes.c_long
    result = query(None, ctypes.byref(info))
    if result != 0:
        raise OSError(result, "Windows could not inspect the Recycle Bin")
    return int(info.i64NumItems), int(info.i64Size)


def _scan() -> tuple[list[CleanupCategory], list[CleanupCandidate], list[CleanupIssue]]:
    specs = _category_specs()
    candidates: list[CleanupCandidate] = []
    issues: list[CleanupIssue] = []
    now = time.time()
    for category in specs:
        if category.mode in ("windows_settings",):
            _append_issue(issues, category.key, "Windows Settings",
                          "Open Windows Storage settings to review update cleanup.")
            continue
        if category.mode == "recycle_bin":
            try:
                count, size = _recycle_bin_info()
                if count:
                    candidates.append(CleanupCandidate(category.key, size=size, item_count=count, kind="recycle_bin"))
            except (OSError, AttributeError) as error:
                _append_issue(issues, category.key, "Recycle Bin", f"Could not inspect Recycle Bin: {error}")
            continue
        if category.mode == "files":
            if not category.roots:
                _append_issue(issues, category.key, "", "No app-specific cleanup location is configured.")
                continue
            for root in category.roots:
                found, count, _size = _walk_root(category, root, now, issues)
                candidates.extend(found)
                if count > MAX_ITEMS_PER_CATEGORY:
                    break
            continue
        if category.mode == "empty_folders":
            for root in category.roots:
                found, _count, _size = _walk_root(category, root, now, issues)
                candidates.extend(found)
            continue
        if category.mode == "delivery_cache":
            if not category.roots:
                continue
            root = category.roots[0]
            if not root.exists():
                continue
            found, count, size = _walk_root(category, root, now, issues, collect=False)
            # Keep the explicit Windows cleanup action available even if the scanner
            # cannot enumerate its protected or hidden cache directory.
            candidates.append(CleanupCandidate(category.key, str(root), str(root), size,
                                               item_count=max(1, count), kind="delivery_cache"))
    return specs, candidates, issues


def _same_path(left: str | Path, right: str | Path) -> bool:
    return os.path.normcase(os.path.abspath(str(left))) == os.path.normcase(os.path.abspath(str(right)))


def _validate_candidate(candidate: CleanupCandidate, specs: list[CleanupCategory]) -> tuple[bool, str]:
    category = next((spec for spec in specs if spec.key == candidate.category), None)
    if category is None:
        return False, "Cleanup category no longer exists."
    roots = category.roots
    if not any(_same_path(candidate.root, root) for root in roots):
        return False, "The cleanup location is no longer an approved location for this category."
    root = Path(candidate.root)
    path = Path(candidate.path)
    try:
        root_stat = os.lstat(root)
        if not stat.S_ISDIR(root_stat.st_mode) or _is_reparse(root_stat):
            return False, "The cleanup root changed or became a reparse point."
        target_abs = os.path.abspath(path)
        root_abs = os.path.abspath(root)
        if _same_path(target_abs, root_abs):
            return False, "The cleanup root itself cannot be removed."
        if os.path.commonpath((os.path.normcase(root_abs), os.path.normcase(target_abs))) != os.path.normcase(root_abs):
            return False, "The item is no longer inside its approved cleanup location."
        current = path
        while True:
            st = os.lstat(current)
            if _is_reparse(st):
                return False, "Skipped symbolic link or reparse point."
            if _same_path(current, path):
                expected_type = stat.S_ISDIR(st.st_mode) if candidate.is_directory else stat.S_ISREG(st.st_mode)
                if not expected_type:
                    return False, "The item type changed after scanning."
                if st.st_size != candidate.size or st.st_mtime_ns != candidate.modified_ns:
                    return False, "The item changed after scanning. Rescan before cleaning it."
                if candidate.inode and getattr(st, "st_ino", 0) and st.st_ino != candidate.inode:
                    return False, "The item was replaced after scanning. Rescan before cleaning it."
            if _same_path(current, root):
                break
            parent = current.parent
            if _same_path(parent, current):
                return False, "Could not validate the item's parent location."
            current = parent
        if _protected_path(path):
            return False, "Skipped protected user data."
        if category.age_days is not None and time.time() - os.lstat(path).st_mtime < category.age_days * 86400:
            return False, "The item is newer than this category's age rule."
        if category.key == "empty_folders":
            with os.scandir(path) as entries:
                if next(entries, None) is not None:
                    return False, "The folder is no longer empty."
        elif not _matches(path, category.patterns):
            return False, "The item no longer matches this category's file rule."
    except (OSError, ValueError) as error:
        return False, f"Could not safely revalidate the item: {error}"
    return True, "Ready"


def _check_not_in_use(path: Path, is_directory: bool) -> tuple[bool, str]:
    """Try an exclusive metadata/read open; conservatively skip anything we cannot lock."""
    if os.name != "nt":
        return False, "Windows file-use validation is unavailable on this platform."
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_file = kernel32.CreateFileW
    create_file.argtypes = [ctypes.c_wchar_p, ctypes.c_ulong, ctypes.c_ulong,
                            ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_void_p]
    create_file.restype = ctypes.c_void_p
    access = 0x80000000 if not is_directory else 0
    flags = 0x02000000 if is_directory else 0x00000080
    handle = create_file(str(path), access, 0, None, 3, flags, None)
    invalid = ctypes.c_void_p(-1).value
    if handle in (None, invalid):
        error = ctypes.get_last_error()
        return False, f"Skipped because the item is in use or cannot be opened exclusively (Windows error {error})."
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel32.CloseHandle(handle)
    return True, "Ready"


def _powershell(script: str) -> subprocess.CompletedProcess[str]:
    encoded = base64.b64encode(script.encode("utf-16le")).decode("ascii")
    return subprocess.run(
        ["powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), check=False,
    )


def _empty_recycle_bin() -> None:
    shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    empty = shell32.SHEmptyRecycleBinW
    empty.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_ulong]
    empty.restype = ctypes.c_long
    # NOCONFIRMATION is safe here: the UI has already asked for separate confirmation.
    result = empty(None, None, 0x00000001 | 0x00000004)
    if result != 0:
        raise OSError(result, "Windows could not empty the Recycle Bin")


def _volume_free_space() -> int:
    if os.name != "nt":
        return 0
    mask = ctypes.windll.kernel32.GetLogicalDrives()
    total = 0
    for index in range(26):
        if mask & (1 << index):
            root = f"{chr(65 + index)}:\\"
            try:
                total += shutil.disk_usage(root).free
            except OSError:
                continue
    return total


class JunkScanWorker(QThread):
    completed = Signal(object, object, object)
    failed = Signal(str)

    def run(self) -> None:
        try:
            specs, candidates, issues = _scan()
            self.completed.emit(specs, candidates, issues)
        except Exception as error:
            self.failed.emit(str(error))


class JunkCleanWorker(QThread):
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, candidates: list[CleanupCandidate], specs: list[CleanupCategory], parent=None):
        super().__init__(parent)
        self.candidates = candidates
        self.specs = specs

    def run(self) -> None:
        try:
            self._run_cleanup()
        except Exception as error:
            self.failed.emit(str(error))

    def _run_cleanup(self) -> None:
        result: dict[str, Any] = {
            "moved": 0, "moved_bytes": 0, "failed": [], "skipped": [],
            "recycle_emptied": False, "recycle_error": "", "delivery_cleaned": False,
            "delivery_error": "", "freed_bytes": 0,
        }
        free_before = _volume_free_space()
        for candidate in self.candidates:
            if candidate.kind == "recycle_bin":
                try:
                    _empty_recycle_bin()
                    result["recycle_emptied"] = True
                except (OSError, AttributeError) as error:
                    result["recycle_error"] = str(error)
                continue
            if candidate.kind == "delivery_cache":
                try:
                    category = next((spec for spec in self.specs if spec.key == candidate.category), None)
                    if category is None or not category.roots or not _same_path(candidate.root, category.roots[0]):
                        result["skipped"].append((candidate.path, "The Windows-managed cache location changed after scanning."))
                        continue
                    current_issues: list[CleanupIssue] = []
                    _found, current_count, current_size = _walk_root(
                        category, Path(candidate.root), time.time(), current_issues, collect=False
                    )
                    if current_count != candidate.item_count or current_size != candidate.size:
                        result["skipped"].append((candidate.path, "The cache changed after scanning. Rescan before cleaning it."))
                        continue
                    script = (
                        "$ErrorActionPreference='Stop'; "
                        "if (-not (Get-Command Delete-DeliveryOptimizationCache -ErrorAction SilentlyContinue)) "
                        "{ throw 'Delivery Optimization cleanup is not available on this Windows installation.' }; "
                        "Delete-DeliveryOptimizationCache -Force; 'Delivery Optimization cache cleanup completed.'"
                    )
                    response = _powershell(script)
                    if response.returncode != 0:
                        raise OSError(response.stderr.strip() or response.stdout.strip() or "Delivery Optimization cleanup failed.")
                    result["delivery_cleaned"] = True
                except (OSError, subprocess.SubprocessError) as error:
                    result["delivery_error"] = str(error)
                continue

            valid, reason = _validate_candidate(candidate, self.specs)
            if not valid:
                result["skipped"].append((candidate.path, reason))
                continue
            available, reason = _check_not_in_use(Path(candidate.path), candidate.is_directory)
            if not available:
                result["skipped"].append((candidate.path, reason))
                continue
            try:
                send_to_recycle_bin(Path(candidate.path))
                if Path(candidate.path).exists():
                    raise OSError("Windows did not move the item out of its cleanup location.")
                result["moved"] += candidate.item_count
                result["moved_bytes"] += candidate.size
            except (OSError, PermissionError) as error:
                result["failed"].append((candidate.path, str(error)))
        free_after = _volume_free_space()
        result["freed_bytes"] = max(0, free_after - free_before)
        self.completed.emit(result)


class JunkCleanerInterface(QWidget):
    COLUMNS = ("Category / item", "Size", "Last modified", "Status")

    def __init__(self, parent_window: QWidget):
        super().__init__()
        self.parent_window = parent_window
        self.worker: JunkScanWorker | JunkCleanWorker | None = None
        self.specs: list[CleanupCategory] = []
        self.candidates: list[CleanupCandidate] = []
        self.issues: list[CleanupIssue] = []
        self.category_items: dict[str, QTreeWidgetItem] = {}
        self._updating_tree = False
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 14)
        layout.setSpacing(10)
        layout.addWidget(TitleLabel("Junk Cleaner"))
        intro = CardWidget(self)
        intro_layout = QVBoxLayout(intro)
        intro_layout.setContentsMargins(14, 10, 14, 10)
        intro_layout.addWidget(BodyLabel(
            "Review cleanup candidates by category. Eligible files are sent to the Recycle Bin first; "
            "space is only reclaimed when the Recycle Bin is emptied. Windows-managed caches use supported cleanup actions."
        ))
        layout.addWidget(intro)

        toolbar = QHBoxLayout()
        self.scan_button = PrimaryPushButton(FluentIcon.SYNC, "Scan cleanup locations", self)
        self.scan_button.setFixedHeight(30)
        self.scan_button.clicked.connect(self.scan)
        toolbar.addWidget(self.scan_button)
        self.clean_button = PushButton(FluentIcon.DELETE, "Clean selected", self)
        self.clean_button.setFixedHeight(30)
        self.clean_button.clicked.connect(self.clean_selected)
        self.clean_button.setEnabled(False)
        toolbar.addWidget(self.clean_button)
        self.settings_button = PushButton(FluentIcon.SETTING, "Windows update cleanup settings", self)
        self.settings_button.setFixedHeight(30)
        self.settings_button.clicked.connect(self.open_windows_cleanup_settings)
        toolbar.addWidget(self.settings_button)
        toolbar.addStretch(1)
        layout.addLayout(toolbar)

        self.status = CaptionLabel("Scanning has not run yet.", self)
        layout.addWidget(self.status)
        self.progress = QProgressBar(self)
        self.progress.setRange(0, 0)
        self.progress.hide()
        layout.addWidget(self.progress)

        card = CardWidget(self)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(10, 8, 10, 10)
        card_layout.addWidget(StrongBodyLabel("Cleanup results"))
        self.tree = QTreeWidget(card)
        self.tree.setColumnCount(len(self.COLUMNS))
        self.tree.setHeaderLabels(self.COLUMNS)
        self.tree.setAlternatingRowColors(True)
        self.tree.setUniformRowHeights(True)
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        header = self.tree.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.tree.itemChanged.connect(self._item_changed)
        card_layout.addWidget(self.tree, 1)
        layout.addWidget(card, 1)
        self._summary = CaptionLabel("", self)
        layout.addWidget(self._summary)

    def scan(self) -> None:
        if self.worker and self.worker.isRunning():
            return
        self.scan_button.setEnabled(False)
        self.clean_button.setEnabled(False)
        self.progress.show()
        self.status.setText("Scanning only the configured cleanup locations…")
        self.worker = JunkScanWorker(self)
        self.worker.completed.connect(self._scan_completed)
        self.worker.failed.connect(self._scan_failed)
        self.worker.start()

    def _scan_completed(self, specs: list[CleanupCategory], candidates: list[CleanupCandidate], issues: list[CleanupIssue]) -> None:
        self.specs, self.candidates, self.issues = specs, candidates, issues
        self.category_items.clear()
        self._updating_tree = True
        self.tree.clear()
        by_category: dict[str, list[int]] = {spec.key: [] for spec in specs}
        for index, candidate in enumerate(candidates):
            by_category.setdefault(candidate.category, []).append(index)
        issue_by_category: dict[str, list[CleanupIssue]] = {spec.key: [] for spec in specs}
        for issue in issues:
            issue_by_category.setdefault(issue.category, []).append(issue)

        for spec in specs:
            category_item = QTreeWidgetItem(self.tree)
            self.category_items[spec.key] = category_item
            category_item.setData(0, Qt.ItemDataRole.UserRole, ("category", spec.key))
            category_item.setToolTip(0, spec.description)
            category_item.setFlags(category_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            category_item.setCheckState(0, Qt.CheckState.Unchecked)
            if spec.mode == "windows_settings":
                category_item.setFlags(category_item.flags() & ~Qt.ItemFlag.ItemIsUserCheckable)
            child_indices = by_category.get(spec.key, [])
            cat_issues = issue_by_category.get(spec.key, [])
            for candidate_index in child_indices:
                candidate = candidates[candidate_index]
                child = QTreeWidgetItem(category_item)
                child.setData(0, Qt.ItemDataRole.UserRole, ("candidate", candidate_index))
                if candidate.kind in ("file", "empty_folder"):
                    full_path = Path(candidate.path)
                    try:
                        display = str(full_path.relative_to(Path(candidate.root)))
                    except ValueError:
                        display = full_path.name
                    child.setText(0, display or full_path.name)
                    child.setText(1, format_bytes(candidate.size))
                    child.setText(2, datetime.fromtimestamp(candidate.modified_ns / 1e9).strftime("%m-%d-%Y %H:%M"))
                    child.setText(3, "Ready")
                    child.setToolTip(0, candidate.path)
                    child.setFlags(child.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                    child.setCheckState(0, Qt.CheckState.Unchecked)
                elif candidate.kind == "recycle_bin":
                    child.setText(0, f"{candidate.item_count:,} deleted item(s) — emptying is permanent")
                    child.setText(1, format_bytes(candidate.size))
                    child.setText(3, "Separate warning")
                    child.setFlags(child.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                    child.setCheckState(0, Qt.CheckState.Unchecked)
                elif candidate.kind == "delivery_cache":
                    child.setText(0, "Windows-managed cache — individual files are not deleted directly")
                    child.setText(1, format_bytes(candidate.size))
                    child.setText(3, f"{candidate.item_count:,} file(s); advanced action")
                    child.setToolTip(0, candidate.path)
                    child.setFlags(child.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                    child.setCheckState(0, Qt.CheckState.Unchecked)
            for issue in cat_issues:
                item = QTreeWidgetItem(category_item)
                item.setText(0, issue.path or issue.reason)
                item.setText(3, issue.reason)
                item.setToolTip(0, issue.path or issue.reason)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsUserCheckable)
            if not child_indices and not cat_issues:
                item = QTreeWidgetItem(category_item)
                if spec.mode == "windows_settings":
                    item.setText(0, "Review eligible Windows Update cleanup in Windows Settings.")
                elif not spec.roots:
                    item.setText(0, "No safe location is configured for automatic scanning.")
                else:
                    item.setText(0, "No eligible items found for this category's rules.")
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsUserCheckable)
            self._update_category_row(spec.key)
            category_item.setExpanded(False)

        self._updating_tree = False
        self.progress.hide()
        self.scan_button.setEnabled(True)
        self.status.setText(f"Scanned {len(specs)} categories · {len(candidates)} review item(s) · {len(issues)} skipped or informational item(s).")
        self._update_totals()

    def _scan_failed(self, message: str) -> None:
        self.progress.hide()
        self.scan_button.setEnabled(True)
        self.status.setText("Cleanup scan failed.")
        QMessageBox.critical(self, "Cleanup scan failed", message)

    def _item_changed(self, item: QTreeWidgetItem, _column: int) -> None:
        if self._updating_tree:
            return
        marker = item.data(0, Qt.ItemDataRole.UserRole)
        if not marker:
            return
        kind, key = marker
        self._updating_tree = True
        if kind == "category":
            state = item.checkState(0)
            for index in range(item.childCount()):
                child = item.child(index)
                child_data = child.data(0, Qt.ItemDataRole.UserRole)
                if child_data and child_data[0] == "candidate":
                    child.setCheckState(0, state)
        elif kind == "candidate":
            parent = item.parent()
            states = [parent.child(i).checkState(0) for i in range(parent.childCount())
                      if parent.child(i).data(0, Qt.ItemDataRole.UserRole)
                      and parent.child(i).data(0, Qt.ItemDataRole.UserRole)[0] == "candidate"]
            if states and all(state == Qt.CheckState.Checked for state in states):
                parent.setCheckState(0, Qt.CheckState.Checked)
            elif states and all(state == Qt.CheckState.Unchecked for state in states):
                parent.setCheckState(0, Qt.CheckState.Unchecked)
            elif states:
                parent.setCheckState(0, Qt.CheckState.PartiallyChecked)
        self._updating_tree = False
        # Updating category summary text emits itemChanged too. Keep the
        # checkbox handler guarded so a partially selected category cannot
        # overwrite each child's individual checked state.
        self._updating_tree = True
        for category_key in self.category_items:
            self._update_category_row(category_key)
        self._updating_tree = False
        self._update_totals()

    def _checked_candidates(self) -> list[CleanupCandidate]:
        selected: list[CleanupCandidate] = []
        for spec in self.specs:
            parent = self.category_items.get(spec.key)
            if not parent:
                continue
            for index in range(parent.childCount()):
                child = parent.child(index)
                marker = child.data(0, Qt.ItemDataRole.UserRole)
                if marker and marker[0] == "candidate" and child.checkState(0) == Qt.CheckState.Checked:
                    selected.append(self.candidates[marker[1]])
        return selected

    def _update_category_row(self, category_key: str) -> None:
        parent = self.category_items.get(category_key)
        if not parent:
            return
        spec = next((entry for entry in self.specs if entry.key == category_key), None)
        if not spec:
            return
        files = [candidate for candidate in self.candidates if candidate.category == category_key]
        selected = [candidate for candidate in self._checked_candidates() if candidate.category == category_key]
        issues = [issue for issue in self.issues if issue.category == category_key]
        item_count = sum(candidate.item_count for candidate in files)
        selected_count = sum(candidate.item_count for candidate in selected)
        total_size = sum(candidate.size for candidate in files)
        selected_size = sum(candidate.size for candidate in selected)
        parent.setText(0, f"{spec.label} · {item_count:,} item(s) · {selected_count:,} selected · {len(issues):,} skipped/info")
        parent.setText(1, format_bytes(total_size))
        parent.setText(2, "")
        parent.setText(3, f"Selected: {format_bytes(selected_size)}")

    def _update_totals(self) -> None:
        selected = self._checked_candidates()
        count = sum(candidate.item_count for candidate in selected)
        size = sum(candidate.size for candidate in selected)
        skipped = sum(1 for issue in self.issues if issue.category != "update_cleanup")
        self._summary.setText(
            f"Selected: {count:,} item(s) · estimated recoverable size: {format_bytes(size)} · "
            f"skipped/protected/inaccessible entries: {skipped:,}. Full paths are available in tooltips."
        )
        self.clean_button.setEnabled(bool(selected) and not (self.worker and self.worker.isRunning()))

    def clean_selected(self) -> None:
        if self.worker and self.worker.isRunning():
            return
        selected = self._checked_candidates()
        if not selected:
            QMessageBox.information(self, "Nothing selected", "Select one or more cleanup items to continue.")
            return
        categories: dict[str, tuple[int, int]] = {}
        for candidate in selected:
            count, size = categories.get(candidate.category, (0, 0))
            categories[candidate.category] = (count + candidate.item_count, size + candidate.size)
        lines = [
            f"{next(spec.label for spec in self.specs if spec.key == key)}: {count:,} item(s), {format_bytes(size)}"
            for key, (count, size) in categories.items()
        ]
        answer = QMessageBox.warning(
            self, "Confirm cleanup",
            "Selected cleanup actions:\n\n" + "\n".join(lines) +
            "\n\nRegular files will be moved to the Recycle Bin where possible. "
            "This may not free disk space until the Recycle Bin is emptied.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        if any(candidate.kind == "recycle_bin" for candidate in selected):
            answer = QMessageBox.warning(
                self, "Permanently empty the Recycle Bin?",
                "This permanently removes the items already in the Recycle Bin and removes their normal recovery option. Continue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return

        self.clean_button.setEnabled(False)
        self.scan_button.setEnabled(False)
        self.progress.show()
        self.status.setText("Revalidating selected items and applying cleanup…")
        self.worker = JunkCleanWorker(selected, self.specs, self)
        self.worker.completed.connect(self._clean_completed)
        self.worker.start()

    def _clean_completed(self, result: dict[str, Any]) -> None:
        self.progress.hide()
        self.scan_button.setEnabled(True)
        def reason_label(reason: str, failed: bool = False) -> str:
            reason = reason.casefold()
            if "in use" in reason or "exclusively" in reason:
                return "in use"
            if "protected" in reason:
                return "protected"
            if "changed" in reason or "replaced" in reason:
                return "changed since scan"
            if "symbolic" in reason or "reparse" in reason:
                return "link skipped"
            if "age rule" in reason or "newer than" in reason:
                return "does not meet age rule"
            if "empty" in reason or "file rule" in reason:
                return "no longer eligible"
            if "approved location" in reason or "inside its approved" in reason:
                return "location is no longer eligible"
            if "permission" in reason or "access denied" in reason:
                return "access denied"
            return "operation error" if failed else "could not safely revalidate"

        def summarize_reasons(entries: list[tuple[Path, str]], failed: bool = False) -> str:
            counts: dict[str, int] = {}
            for _path, reason in entries:
                label = reason_label(str(reason), failed)
                counts[label] = counts.get(label, 0) + 1
            if not counts:
                return "none"
            labels = [label.title() for label in counts]
            if len(labels) == 1:
                return labels[0]
            return ", ".join(
                f"{label.title()} ({count})"
                for label, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
            )

        skipped_count = len(result["skipped"])
        failed_count = len(result["failed"])
        lines = [
            f"Moved to Recycle Bin: {result['moved']:,} item(s), {format_bytes(result['moved_bytes'])}.",
            f"Measured disk space freed: {format_bytes(result['freed_bytes'])}.",
            f"Skipped after revalidation: {skipped_count:,}" +
            (f" (Reason: {summarize_reasons(result['skipped'])})" if skipped_count else "") + ".",
            f"Failed: {failed_count:,}" +
            (f" (Reason: {summarize_reasons(result['failed'], failed=True)})" if failed_count else "") + ".",
        ]
        if result["recycle_emptied"]:
            lines.append("Recycle Bin emptied after the separate permanent-deletion warning.")
        if result["recycle_error"]:
            lines.append("Recycle Bin cleanup failed: " + result["recycle_error"])
        if result["delivery_cleaned"]:
            lines.append("Delivery Optimization cache cleanup completed through Windows.")
        if result["delivery_error"]:
            lines.append("Delivery Optimization cleanup failed: " + result["delivery_error"])
        detail = "\n".join(lines)
        self.status.setText(
            f"Cleanup complete · {result['moved']:,} item(s) moved · {len(result['skipped'])} skipped · {len(result['failed'])} failed."
        )
        self.parent_window.log_activity("Junk file cleanup", detail)
        QMessageBox.information(self, "Cleanup results", detail)
        self.scan()

    def open_windows_cleanup_settings(self) -> None:
        if not QDesktopServices.openUrl(QUrl("ms-settings:storagerecommendations")):
            QMessageBox.information(
                self, "Windows cleanup settings",
                "Open Settings → System → Storage → Cleanup recommendations to review Windows Update cleanup.",
            )
