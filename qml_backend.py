"""Python services exposed to the FileSense Qt Quick interface."""

from __future__ import annotations

import fnmatch
import os
import re
import shutil
import threading
import time
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

from PySide6.QtCore import (QObject, Property, QSettings, QStorageInfo, Signal, Slot, QThread,
                            QUrl, QFileInfo, QBuffer, QByteArray, QIODevice)
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import QFileIconProvider

from activity_log import log_activity
from app_common import (
    CATEGORIES, CONFLICT_POLICIES, DUPLICATES_FOLDER, SIZE_UNITS,
    StorageFile, StorageScanWorker, file_type, format_bytes, move_with_replace,
    resource_path, send_to_recycle_bin, unique_conflict_path,
    allocated_file_size, fast_windows_entries, is_ntfs_path, volume_allocation_unit,
)
from file_search import FileSearchWorker, SearchCriteria, _is_reparse, _is_within, _norm_path
from junk_cleaner import JunkCleanWorker, JunkScanWorker
from startup_manager import AutorunScanWorker, TAB_CATEGORIES, StartupConfirmationRequired, _set_enabled
from license_manager import activate as activate_license, license_status, machine_fingerprint


_startup_icon_provider = None
_startup_icon_cache: dict[str, str] = {}


def _startup_icon_data(executable: str) -> str:
    """Return the executable's Windows shell icon as a small cached PNG data URL."""
    global _startup_icon_provider
    path = str(executable or "").strip()
    if not path or path == "—":
        return ""
    cache_key = os.path.normcase(os.path.abspath(os.path.expandvars(path)))
    if cache_key in _startup_icon_cache:
        return _startup_icon_cache[cache_key]
    if not os.path.isfile(cache_key):
        _startup_icon_cache[cache_key] = ""
        return ""
    try:
        if _startup_icon_provider is None:
            _startup_icon_provider = QFileIconProvider()
        icon = _startup_icon_provider.icon(QFileInfo(cache_key))
        pixmap = icon.pixmap(28, 28)
        if pixmap.isNull():
            return ""
        image_bytes = QByteArray()
        buffer = QBuffer(image_bytes)
        if not buffer.open(QIODevice.OpenModeFlag.WriteOnly):
            return ""
        pixmap.save(buffer, "PNG")
        buffer.close()
        encoded = bytes(image_bytes.toBase64()).decode("ascii")
        result = "data:image/png;base64," + encoded
    except Exception:
        result = ""
    _startup_icon_cache[cache_key] = result
    return result


def _parse_ui_date(value: str) -> datetime:
    """Parse the app's visible date format, while accepting old ISO values."""
    value = value.strip()
    for date_format in ("%m-%d-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, date_format)
        except ValueError:
            pass
    raise ValueError(value)


def _compact_activity_detail(action: str, details: str) -> str:
    """Keep activity history focused on outcomes and reasons, not file lists."""
    action = str(action or "").strip()
    detail = str(details or "").strip()
    if not detail:
        return ""

    # Older duplicate cleanup logs appended every removed path to the summary.
    detail = detail.split("Removed paths:", 1)[0].strip()
    if action.startswith("Autorun:"):
        item_name = detail.split(";", 1)[0].strip()
        return f"Startup item updated: {item_name}." if item_name else "Startup item updated."
    if action == "Storage scan":
        if ";" in detail:
            detail = "Scanned " + detail.split(";", 1)[1].strip()
        else:
            detail = re.sub(r"^Scanned .+?: (?=\d)", "Scanned ", detail)
    elif action == "Quick Organize" and "moved " in detail.casefold():
        detail = detail[detail.casefold().rfind("moved "):]
    elif action.startswith("Build rule:") and "Moved " in detail:
        detail = detail[detail.rfind("Moved "):]
    elif action == "File search" and "results:" in detail:
        detail = detail[detail.casefold().rfind("results:"):]

    # Drop path-only lines from older logs and keep each summary item separate.
    summary_lines = []
    for line in detail.splitlines():
        line = line.strip().lstrip("•- ").strip()
        if not line:
            continue
        if re.match(r"^(?:[A-Za-z]:[\\/]|\\\\|/)", line):
            continue
        summary_lines.extend(part.strip() for part in re.split(r"\s*·\s*|\s*;\s*", line) if part.strip())
    if len(summary_lines) > 4:
        summary_lines = summary_lines[:3] + ["…"]
    return "\n".join(summary_lines)


class QuickDiscoveryWorker(QThread):
    completed = Signal(object, str)

    def __init__(self, kind: str, root: Path, conditions=None):
        super().__init__()
        self.kind, self.root = kind, root
        self.conditions = conditions or []
        self.groups = {}
        self.excluded_paths = []

    def run(self):
        rows = []
        groups = defaultdict(list)
        errors = []
        include_subfolders = getattr(self, "include_subfolders", True)
        cutoff = time.time() - 30 * 86400
        try:
            roots = tuple(x.strip() for x in str(self.root).split(";") if x.strip())
            roots = __import__("file_search")._collapse_roots(roots)
            excluded = {os.path.normcase(os.path.abspath(path)) for path in self.excluded_paths}

            def is_excluded(path):
                candidate = os.path.normcase(os.path.abspath(path))
                return any(candidate == item or candidate.startswith(item + os.sep) for item in excluded)

            seen = set()
            for root in roots:
                if not root.is_dir():
                    errors.append(f"Folder not found: {root}")
                    continue
                def onerror(error):
                    errors.append(str(error))
                for base, dirs, files in os.walk(root, topdown=True, followlinks=False, onerror=onerror):
                    current = Path(base)
                    if is_excluded(current):
                        dirs[:] = []
                        continue
                    dirs[:] = [name for name in dirs if not is_excluded(current / name)]
                    if not include_subfolders and current != root:
                        dirs[:] = []
                        continue
                    try:
                        relative = current.relative_to(root)
                    except ValueError:
                        dirs[:] = []
                        continue
                    if relative.parts and relative.parts[0].casefold() == DUPLICATES_FOLDER.casefold():
                        dirs[:] = []
                        continue
                    dirs[:] = [name for name in dirs if name.casefold() != DUPLICATES_FOLDER.casefold()]
                    # Duplicate Finder compares file names only. Directory names
                    # are traversal nodes, not duplicate candidates.
                    candidates = [] if self.kind == "duplicates" else [(current / name, True) for name in dirs]
                    candidates.extend((current / name, False) for name in files)
                    if not include_subfolders:
                        dirs[:] = []
                    for path, is_dir in candidates:
                        if is_excluded(path):
                            continue
                        try:
                            info = os.lstat(path)
                            if _is_reparse(info):
                                continue
                            key = os.path.normcase(str(path.resolve()))
                            if key in seen:
                                continue
                            seen.add(key)
                        except OSError as error:
                            errors.append(f"{path}: {error}")
                            continue
                        if self.kind == "duplicates":
                            if not FileSenseBackend._matches_duplicate_rule(path, self.conditions):
                                continue
                            groups[path.name.casefold()].append(path)
                            continue
                        if is_dir:
                            continue
                        try:
                            info = path.stat(follow_symlinks=False)
                        except OSError:
                            continue
                        if self.kind == "large" and info.st_size >= 100 * 1024 * 1024:
                            rows.append((info.st_size, path))
                        elif self.kind == "recent" and info.st_mtime >= cutoff:
                            rows.append((info.st_size, path))
            if self.kind == "duplicates":
                duplicate_groups = [sorted(paths, key=lambda p: str(p).casefold())
                                    for paths in groups.values() if len(paths) > 1]
                duplicate_groups.sort(key=lambda group: (group[0].name.casefold(), group[0].is_dir()))
                for group_index, paths in enumerate(duplicate_groups):
                    for path in paths:
                        try:
                            size = path.stat().st_size if path.is_file() else 0
                        except OSError:
                            size = 0
                        rows.append((size, path, str(group_index), "Folder" if path.is_dir() else "File"))
            else:
                rows = [(size, path, "", "File") for size, path in rows]
            if self.kind == "duplicates":
                rows.sort(key=lambda item: (item[2], str(item[1]).casefold()))
            else:
                rows.sort(key=lambda item: item[0], reverse=True)
            self.completed.emit(rows, "; ".join(errors[:5]) if errors else "")
        except Exception as error:
            self.completed.emit([], str(error))


class StorageDirectoryFilesWorker(QThread):
    completed = Signal(str, object, str)

    def __init__(self, path: Path, fast_ntfs: bool):
        super().__init__()
        self.path = Path(path)
        self.fast_ntfs = fast_ntfs

    def run(self):
        files = []
        error_text = ""
        try:
            allocation_unit = volume_allocation_unit(self.path)
            if self.fast_ntfs:
                for name, attributes, size in fast_windows_entries(self.path):
                    if attributes & 0x10 or attributes & 0x400:
                        continue
                    entry_path = self.path / name
                    try:
                        if attributes & (0x00000800 | 0x00000200):
                            file_stat = os.stat(entry_path, follow_symlinks=False)
                            allocated = allocated_file_size(str(entry_path), file_stat, allocation_unit)
                        else:
                            allocated = ((size + allocation_unit - 1) // allocation_unit) * allocation_unit if size else 0
                        extension = os.path.splitext(name)[1].casefold() or "(No Extension)"
                        files.append(StorageFile(entry_path, name, size, allocated, extension))
                    except OSError:
                        continue
            else:
                with os.scandir(self.path) as entries:
                    for entry in entries:
                        try:
                            if entry.is_file(follow_symlinks=False):
                                info = entry.stat(follow_symlinks=False)
                                extension = os.path.splitext(entry.name)[1].casefold() or "(No Extension)"
                                files.append(StorageFile(Path(entry.path), entry.name, info.st_size,
                                                         allocated_file_size(entry.path, info, allocation_unit), extension))
                        except OSError:
                            continue
        except OSError as error:
            error_text = f"Could not list files in {self.path}: {error}"
        files.sort(key=lambda item: item.allocated, reverse=True)
        self.completed.emit(str(self.path), files, error_text)


class FileSenseBackend(QObject):
    changed = Signal()
    confirmationRequested = Signal(str, str)
    startupActionFailed = Signal(str)
    cleanupCompleted = Signal(str)

    def __init__(self):
        super().__init__()
        self.settings = QSettings("ProSoft", "FileSense")
        self._page = "Home"
        self._status = "Ready"
        self._rows: list[dict] = []
        self._extension_rows: list[dict] = []
        self._categories: list[dict] = []
        self._category_flags: dict[str, bool] = {}
        self._workers = []
        self._search_cancel = threading.Event()
        self._search_running = False
        self._search_selected: set[str] = set()
        self._pending_search_delete: list[str] = []
        self._storage_root: Path | None = None
        self._storage_node = None
        self._storage_nodes_by_path = {}
        self._storage_worker = None
        self._storage_file_workers = {}
        self._storage_data_revision = 0
        self._storage_scanning = False
        self._storage_expanded: set[str] = set()
        self._storage_selected: set[str] = set()
        self._storage_fast = False
        self._junk_specs = []
        self._junk_candidates = []
        self._junk_issues = []
        self._junk_indices_by_category: dict[str, list[int]] = {}
        self._junk_view_indices: list[int] = []
        self._junk_current_category: str | None = None
        self._junk_page = 0
        self._junk_page_size = 200
        self._junk_sort_field = "path"
        self._junk_sort_descending = False
        self._junk_scanning = False
        self._junk_cleaning = False
        self._candidate_selected: set[int] = set()
        self._pending_junk_clean = None
        self._pending_junk_recycle_confirmation = False
        self._startup_entries = []
        self._selected_startup: dict = {}
        self._startup_scanning = False
        self._startup_filter = "All"
        self._startup_summary = ""
        self._startup_action_notice = ""
        self._pending_confirmation: tuple[str, str, bool] | None = None
        self._pending_storage_delete: list[str] = []
        self._duplicate_groups: dict[str, list[str]] = {}
        self._duplicate_delete_selected: dict[str, bool] = {}
        self._category_plan: list[dict] = []
        self._rule_plan: list[dict] = []
        self._rule_config: dict = {}

    @Property(str, notify=changed)
    def page(self): return self._page
    @Property(str, notify=changed)
    def status(self): return self._status
    @Property(str, notify=changed)
    def startupActionNotice(self): return self._startup_action_notice
    @Property('QVariantList', notify=changed)
    def rows(self): return self._rows
    @Property('QVariantList', notify=changed)
    def quickOrganizeRows(self): return [dict(row) for row in self._category_plan]
    @Property('QVariantList', notify=changed)
    def ruleRows(self): return [dict(row) for row in self._rule_plan]
    @Property('QVariantList', notify=changed)
    def extensionRows(self): return self._extension_rows
    @Property('QVariantMap', notify=changed)
    def storageVolumeInfo(self):
        if not self._storage_root:
            return {}
        try:
            volume = QStorageInfo(str(self._storage_root))
            if not volume.isValid() or not volume.isReady():
                return {}
            total = max(0, int(volume.bytesTotal()))
            # bytesFree is the volume's actual free space. bytesAvailable is
            # user-available capacity and can be lower when quotas/reserves apply.
            free = max(0, int(volume.bytesFree()))
            used = max(0, total - free)
            raw_fs = volume.fileSystemType()
            try:
                filesystem = bytes(raw_fs).decode("utf-8", errors="replace").strip()
            except Exception:
                filesystem = str(raw_fs).strip()
            return {
                "filesystem": filesystem or "Storage volume",
                "total": format_bytes(total),
                "used": format_bytes(used),
                "free": format_bytes(free),
                "usedPercent": (used * 100.0 / total) if total else 0.0,
            }
        except Exception:
            return {}
    @Property('QVariantList', notify=changed)
    def categories(self): return self._categories
    @Property(bool, notify=changed)
    def searchRunning(self): return self._search_running
    @Property(int, notify=changed)
    def searchSelectionCount(self): return len(self._search_selected)
    @Property(bool, notify=changed)
    def storageHasSelection(self):
        root_key = _norm_path(self._storage_node.path) if self._storage_node else ""
        return any(path != root_key for path in self._storage_selected)
    @Property(bool, notify=changed)
    def storageScanning(self): return self._storage_scanning
    @Property(str, notify=changed)
    def storageRootPath(self):
        return str(self._storage_root or "")
    @Property(bool, notify=changed)
    def storageDirectoryLoading(self):
        return bool(self._storage_file_workers)
    @Property(int, notify=changed)
    def storageDataRevision(self):
        return self._storage_data_revision
    @Property(bool, notify=changed)
    def startupBusy(self): return self._startup_scanning
    @Property(str, notify=changed)
    def startupFilter(self): return self._startup_filter
    @Property(int, notify=changed)
    def startupAppCount(self):
        return sum(1 for entry in self._startup_entries if entry.category == "Startup apps")
    @Property(int, notify=changed)
    def startupAppEnabledCount(self):
        return sum(1 for entry in self._startup_entries if entry.category == "Startup apps"
                   and ("Disabled" if entry.metadata.get("approval_status") == "Disabled" else entry.status) == "Enabled")
    @Property(int, notify=changed)
    def startupAppDisabledCount(self):
        return sum(1 for entry in self._startup_entries if entry.category == "Startup apps"
                   and ("Disabled" if entry.metadata.get("approval_status") == "Disabled" else entry.status) == "Disabled")
    @Property(bool, notify=changed)
    def junkBusy(self): return self._junk_scanning or self._junk_cleaning
    @Property(int, notify=changed)
    def junkSelectionCount(self): return len(self._candidate_selected)
    @Property(int, notify=changed)
    def junkCandidateCount(self): return len(self._junk_candidates)
    @Property(str, notify=changed)
    def junkTotalSizeText(self): return format_bytes(sum(candidate.size for candidate in self._junk_candidates))
    @Property(int, notify=changed)
    def junkPage(self): return self._junk_page
    @Property(str, notify=changed)
    def junkCurrentCategory(self): return self._junk_current_category or ""
    @Property(int, notify=changed)
    def junkPageCount(self): return max(1, (len(self._junk_view_indices) + self._junk_page_size - 1) // self._junk_page_size)
    @Property(int, notify=changed)
    def junkViewCount(self): return len(self._junk_view_indices)
    @Property(str, notify=changed)
    def savedSearchLocations(self):
        value = self.settings.value("file_search_locations", [])
        return ";".join(value if isinstance(value, (list, tuple)) else ([value] if value else []))
    @Property(str, notify=changed)
    def savedSearchExclusions(self):
        value = self.settings.value("file_search_exclusions", [])
        return ";".join(value if isinstance(value, (list, tuple)) else ([value] if value else []))
    @Property('QVariantList', notify=changed)
    def drives(self):
        result = []
        for storage in QStorageInfo.mountedVolumes():
            if storage.isValid() and storage.isReady() and storage.rootPath():
                root = storage.rootPath()
                label = f"{root}  ·  {storage.name()}" if storage.name() else root
                result.append({"label": label, "path": root})
        return result
    @Property(str, notify=changed)
    def licenseLabel(self):
        info = license_status(self.settings)
        return "Activated" if info["state"] == "activated" else f"Trial · {info['days_remaining']} days remaining"
    @Property(bool, notify=changed)
    def licenseExpired(self): return license_status(self.settings)["state"] == "expired"
    @Property(bool, notify=changed)
    def lightAppearance(self): return str(self.settings.value("appearance", "Dark")).casefold() == "light"

    @Slot()
    def toggleAppearance(self):
        self.settings.setValue("appearance", "Dark" if self.lightAppearance else "Light")
        self.settings.sync()
        self.changed.emit()
    @Property(str, notify=changed)
    def machineCode(self): return machine_fingerprint()
    @Property('QVariantMap', notify=changed)
    def selectedStartup(self): return self._selected_startup
    @Property(str, notify=changed)
    def duplicateConfirmationText(self):
        selected = sum(1 for paths in self._duplicate_groups.values() for path in paths
                       if self._duplicate_delete_selected.get(path, False))
        noun = "entry" if selected == 1 else "entries"
        return f"Send {selected} checked {noun} to the Windows Recycle Bin? Unchecked entries will be kept."

    @Slot()
    def copyMachineCode(self): QGuiApplication.clipboard().setText(self.machineCode)

    @Slot(str)
    def activate(self, key):
        success, message = activate_license(self.settings, key)
        self._status = message
        self.changed.emit()

    @Slot(str, str, bool, str)
    def previewOrganize(self, source, exclusions, include_subfolders, conflict_policy):
        root = Path(source.strip()).expanduser()
        try:
            root = root.resolve(strict=True)
            if not root.is_dir() or _is_reparse(os.lstat(root)):
                raise ValueError("Choose a valid source folder.")
            excluded = [Path(value.strip()).expanduser().resolve(strict=True)
                        for value in exclusions.split(";") if value.strip()]
            if any(not item.is_dir() or not item.is_relative_to(root) for item in excluded):
                raise ValueError("Excluded folders must exist inside the selected source folder.")
        except (OSError, ValueError) as error:
            self._category_plan = []
            self._rows = []
            self._status = str(error) or "Choose a valid source folder."
            self.changed.emit()
            return

        excluded = tuple(_norm_path(item) for item in excluded)
        category_folders = {name.casefold() for name in CATEGORIES} | {"others"}
        paths = []
        try:
            if include_subfolders:
                def on_walk_error(error):
                    raise error
                for current, dirs, files in os.walk(root, topdown=True, followlinks=False, onerror=on_walk_error):
                    current_path = Path(current)
                    dirs.sort(key=str.casefold)
                    dirs[:] = [name for name in dirs
                               if not (current_path == root and name.casefold() in category_folders)
                               and not _is_reparse(os.lstat(current_path / name))
                               and not any(_is_within(_norm_path(current_path / name), blocked) for blocked in excluded)]
                    if any(_is_within(_norm_path(current_path), blocked) for blocked in excluded):
                        continue
                    for name in sorted(files, key=str.casefold):
                        path = current_path / name
                        try:
                            if path.is_file() and not _is_reparse(os.lstat(path)):
                                paths.append(path)
                        except OSError:
                            continue
            else:
                paths = [item for item in sorted(root.iterdir(), key=lambda path: path.name.casefold())
                         if item.is_file() and not _is_reparse(os.lstat(item))
                         and not any(_is_within(_norm_path(item), blocked) for blocked in excluded)]
        except OSError as error:
            self._category_plan = []
            self._rows = []
            self._status = f"Could not scan folder: {error}"
            self.changed.emit()
            return

        plan = []
        requested_seen: set[str] = set()
        reserved: set[str] = set()
        for path in paths:
            category = next((name for name, exts in CATEGORIES.items() if path.suffix.casefold() in exts), "Others")
            requested = root / category / path.name
            key = os.path.normcase(str(requested))
            conflict = requested.exists() or key in requested_seen
            requested_seen.add(key)
            row = {"name": path.name, "type": category, "size": format_bytes(path.stat().st_size),
                   "path": str(path), "category": category, "requested": str(requested),
                   "destination": str(unique_conflict_path(requested, reserved) if conflict and conflict_policy == "Keep both" else requested),
                   "destinationExists": conflict, "conflict": conflict,
                   "policy": conflict_policy if conflict else "—"}
            reserved.add(os.path.normcase(row["destination"]))
            plan.append(row)
        self._category_plan = plan
        self._category_default_policy = conflict_policy
        self._category_config = {"root": str(root), "excluded": list(excluded), "include_subfolders": include_subfolders}
        self._rows = [dict(row) for row in plan]
        self._status = f"{len(plan):,} file(s) ready for Quick Organize."
        self.changed.emit()

    @Slot(str, str)
    def setCategoryPolicy(self, path, policy):
        if policy not in CONFLICT_POLICIES:
            return
        row = next((item for item in self._category_plan if item.get("path") == path), None)
        if row is None:
            return
        row["policy"] = policy
        self._refresh_category_rows()

    @Slot(str)
    def setDefaultCategoryPolicy(self, policy):
        if policy not in CONFLICT_POLICIES:
            return
        self._category_default_policy = policy
        for row in self._category_plan:
            if row.get("conflict"):
                row["policy"] = policy
        self._refresh_category_rows()

    def _refresh_category_rows(self):
        reserved: set[str] = set()
        for row in self._category_plan:
            requested = Path(row["requested"])
            destination = requested
            if row["conflict"] and row["policy"] == "Keep both":
                destination = unique_conflict_path(requested, reserved)
            row["destination"] = str(destination)
            reserved.add(os.path.normcase(str(destination)))
        self._rows = [dict(row) for row in self._category_plan]
        self.changed.emit()

    @Slot()
    def organizeFiles(self):
        moved = skipped = failed = 0
        root = Path(self._category_config.get("root", "")) if hasattr(self, "_category_config") else None
        excluded = self._category_config.get("excluded", []) if hasattr(self, "_category_config") else []
        for row in self._category_plan:
            source, requested = Path(row["path"]), Path(row["requested"])
            policy = row["policy"] if row["conflict"] else self._category_default_policy
            try:
                if root is None or not source.is_file() or _is_reparse(os.lstat(source)) or not _is_within(source.resolve(), root):
                    skipped += 1
                    continue
                if any(_is_within(_norm_path(source), blocked) for blocked in excluded):
                    skipped += 1
                    continue
                category = next((name for name, exts in CATEGORIES.items() if source.suffix.casefold() in exts), "Others")
                if category != row["category"]:
                    skipped += 1
                    continue
                destination = requested
                if destination.exists():
                    if policy == "Skip":
                        skipped += 1
                        continue
                    if policy == "Keep both":
                        destination = unique_conflict_path(destination)
                if os.path.normcase(str(source.resolve())) == os.path.normcase(str(destination.resolve())):
                    skipped += 1
                    continue
                destination.parent.mkdir(parents=True, exist_ok=True)
                if policy == "Replace" and destination.exists():
                    move_with_replace(source, destination)
                else:
                    shutil.move(str(source), str(destination))
                moved += 1
            except OSError:
                failed += 1
        self._status = f"Moved {moved:,} · skipped {skipped:,} · failed {failed:,}."
        log_activity(self, "Quick Organize", self._status)
        self._category_plan = []
        self._rows = []
        self.changed.emit()

    @Slot(str, bool, 'QVariantList', str, str, str)
    def previewRule(self, roots_text, include_subfolders, conditions, action, destination, conflict_policy):
        roots = tuple(value.strip() for value in roots_text.split(";") if value.strip())
        roots = tuple(str(path) for path in __import__("file_search")._collapse_roots(roots))
        if not roots:
            self._rule_plan = []; self._rows = []; self._status = "Add at least one monitored folder."; self.changed.emit(); return
        if any(not Path(root).expanduser().is_dir() for root in roots):
            self._rule_plan = []; self._rows = []; self._status = "Choose existing monitored source folders."; self.changed.emit(); return
        if action != "Delete file" and (
            not destination.strip()
            or not Path(destination.strip()).expanduser().is_dir()
        ):
            self._rule_plan = []; self._rows = []; self._status = "Choose an existing destination folder."; self.changed.emit(); return
        if not conditions:
            self._rule_plan = []; self._rows = []; self._status = "Add at least one condition."; self.changed.emit(); return
        try:
            conditions = [self._rule_condition_map(item) for item in conditions]
            plan = []
            requested_seen: set[str] = set()
            reserved: set[str] = set()
            for path in self._iter_rule_files(roots, include_subfolders):
                if not self._matches_rule(path, conditions):
                    continue
                requested = Path(destination.strip()).expanduser() / path.name if action != "Delete file" else None
                conflict = False
                same_source = False
                effective = None
                if requested is not None:
                    same_source = os.path.normcase(str(path.resolve())) == os.path.normcase(str(requested.resolve()))
                    key = os.path.normcase(str(requested.resolve()))
                    conflict = requested.exists() or key in requested_seen
                    requested_seen.add(key)
                    effective = requested
                    if conflict and not same_source and conflict_policy == "Keep both":
                        effective = unique_conflict_path(requested, reserved)
                    reserved.add(os.path.normcase(str(effective.resolve())))
                plan.append({"name": path.name, "type": file_type(path), "size": format_bytes(path.stat().st_size),
                             "path": str(path), "destination": str(effective) if effective else "—",
                             "requested": str(requested) if requested else "", "conflict": conflict and not same_source,
                             "sameSource": same_source, "policy": conflict_policy if conflict and not same_source else "—",
                             "action": action})
            self._rule_plan = plan
            self._rule_conditions = [dict(item) for item in conditions]
            self._rule_config = {"roots": roots, "include_subfolders": include_subfolders, "action": action,
                                 "destination": destination.strip(), "conflict_policy": conflict_policy}
            self._rows = [dict(row) for row in plan]
            self._status = f"{len(plan):,} file(s) match the rule."
        except Exception as error:
            self._rule_plan = []; self._rows = []; self._status = f"Could not preview rule: {error}"
        self.changed.emit()

    @staticmethod
    def _rule_condition_map(condition):
        if isinstance(condition, dict):
            return dict(condition)
        # QML ListModel.get() may cross the PySide boundary as a QObject.
        property_names = (
            "logic", "field", "operator", "typeValue", "value", "unit",
            "dateKind", "startDate", "endDate", "period", "periodUnit",
        )
        read_property = getattr(condition, "property", None)
        if callable(read_property):
            return {name: read_property(name) for name in property_names}
        raise ValueError("Could not read a rule condition. Please review the condition fields and try again.")

    @Slot(str, bool, 'QVariantList', str, str, str)
    def prepareRuleRun(self, roots_text, include_subfolders, conditions, action, destination, conflict_policy):
        """Refresh matches from current controls, retaining per-file policy choices."""
        saved_policies = {
            _norm_path(Path(row["path"]).resolve()): row["policy"]
            for row in self._rule_plan
            if row.get("conflict") and row.get("path")
        }
        self.previewRule(roots_text, include_subfolders, conditions, action, destination, conflict_policy)
        if not self._rule_plan:
            return
        for row in self._rule_plan:
            key = _norm_path(Path(row["path"]).resolve())
            if row.get("conflict") and key in saved_policies:
                row["policy"] = saved_policies[key]
        self._refresh_rule_plan()

    def _iter_rule_files(self, roots, include_subfolders):
        seen = set()
        for raw in roots:
            root = Path(raw).resolve(strict=True)
            if not root.is_dir() or _is_reparse(os.lstat(root)):
                continue
            if include_subfolders:
                for current, dirs, files in os.walk(root, topdown=True, followlinks=False):
                    current_path = Path(current)
                    dirs[:] = [name for name in dirs if name.casefold() != DUPLICATES_FOLDER.casefold()
                               and not _is_reparse(os.lstat(current_path / name))]
                    for name in files:
                        path = current_path / name
                        try:
                            if not path.is_file() or _is_reparse(os.lstat(path)): continue
                            key = _norm_path(path.resolve())
                            if key not in seen:
                                seen.add(key); yield path
                        except OSError: continue
            else:
                for path in root.iterdir():
                    try:
                        if path.is_file() and not _is_reparse(os.lstat(path)):
                            key = _norm_path(path.resolve())
                            if key not in seen:
                                seen.add(key); yield path
                    except OSError: continue

    @staticmethod
    def _matches_rule(path, conditions):
        values = []
        for condition in conditions:
            field = condition.get("field", "File Type")
            operator = condition.get("operator", "Is")
            value = str(condition.get("value", "")).strip()
            if field == "File Type":
                expected = str(condition.get("typeValue", "")).strip()
                if not expected: raise ValueError("Choose a file type for each File Type condition.")
                actual, wanted = file_type(path).casefold(), expected.casefold()
                result = wanted in actual if operator == "Contains" else wanted not in actual if operator == "Does not contain" else actual == wanted if operator == "Is" else actual != wanted
            elif field == "File Extension":
                if not value: raise ValueError("Enter a value for every condition.")
                wanted = value.casefold()
                if not wanted.startswith("."): wanted = "." + wanted
                actual = path.name.casefold()
                result = wanted in actual if operator == "Contains" else wanted not in actual if operator == "Does not contain" else actual.endswith(wanted) if operator == "Is" else not actual.endswith(wanted)
            elif field == "File Size":
                if not value: raise ValueError("Enter a value for every condition.")
                try: limit = float(value) * SIZE_UNITS[str(condition.get("unit", "MB"))]
                except (ValueError, KeyError) as error: raise ValueError("File Size needs a numeric value and size unit.") from error
                size = path.stat().st_size
                result = {"Is": size == limit, "Is not": size != limit, "Greater than": size > limit,
                          "Less than": size < limit, "At least": size >= limit, "At most": size <= limit}[operator]
            elif field == "File Name":
                if not value: raise ValueError("Enter a value for every condition.")
                expected = value.casefold(); actual = path.name.casefold()
                filename_without_extension = path.stem.casefold()
                result = {"Contains": expected in actual, "Does not contain": expected not in actual,
                          "Starts with": actual.startswith(expected), "Ends with": filename_without_extension.endswith(expected),
                          "Matches exact text": actual == expected,
                          "Matches pattern (advanced)": fnmatch.fnmatchcase(actual, expected)}[operator]
            else:
                stat = path.stat()
                stamp = {"Date created": stat.st_ctime, "Date modified": stat.st_mtime,
                         "Date last accessed": stat.st_atime}[condition.get("dateKind", "Date modified")]
                actual = datetime.fromtimestamp(stamp)
                if operator in ("Before", "After", "Between"):
                    try:
                        start = _parse_ui_date(condition.get("startDate", "")).date()
                        end_text = condition.get("endDate", "")
                        end = _parse_ui_date(end_text).date() if end_text else start
                    except ValueError as error: raise ValueError("Enter rule dates in MM-DD-YYYY format.") from error
                    if operator == "Before": result = actual.date() < start
                    elif operator == "After": result = actual.date() > start
                    else:
                        if end < start: raise ValueError("The end date must not be before the start date.")
                        result = start <= actual.date() <= end
                else:
                    try: amount = int(condition.get("period", 7))
                    except (ValueError, TypeError) as error: raise ValueError("Enter a numeric date period.") from error
                    factor = {"Days": 1, "Months": 30, "Years": 365}.get(condition.get("periodUnit", "Days"), 1)
                    now = datetime.now(); cutoff = now - timedelta(days=amount * factor)
                    result = {"Within last": cutoff <= actual <= now, "Older than": actual < cutoff,
                              "Newer than": actual > cutoff}[operator]
            values.append(bool(result))
        if not values: return True
        result = values[0]
        for index in range(1, len(values)):
            logic = conditions[index].get("logic", "AND")
            result = result and values[index] if logic == "AND" else result or values[index] if logic == "OR" else result and not values[index]
        return result

    @Slot(str, str)
    def setRulePolicy(self, path, policy):
        if policy not in CONFLICT_POLICIES: return
        row = next((item for item in self._rule_plan if item.get("path") == path), None)
        if row is None: return
        row["policy"] = policy
        self._refresh_rule_plan()

    @Slot(str)
    def setDefaultRulePolicy(self, policy):
        if policy not in CONFLICT_POLICIES:
            return
        if hasattr(self, "_rule_config"):
            self._rule_config["conflict_policy"] = policy
        for row in self._rule_plan:
            if row.get("conflict"):
                row["policy"] = policy
        self._refresh_rule_plan()

    def _refresh_rule_plan(self):
        reserved = set()
        for row in self._rule_plan:
            if not row["requested"]: continue
            requested = Path(row["requested"]); destination = requested
            if row["conflict"] and row["policy"] == "Keep both": destination = unique_conflict_path(requested, reserved)
            row["destination"] = str(destination)
            reserved.add(os.path.normcase(str(destination.resolve())))
        self._rows = [dict(row) for row in self._rule_plan]
        self.changed.emit()

    @Slot()
    def runRule(self):
        roots = self._rule_config.get("roots", ())
        if not roots or any(not Path(root).expanduser().is_dir() for root in roots):
            self._status = "Choose existing monitored source folders before running the rule."
            self.changed.emit()
            return
        moved = copied = deleted = skipped = failed = 0
        action = self._rule_config.get("action", "Move file")
        destination = str(self._rule_config.get("destination", "")).strip()
        target = Path(destination).expanduser() if action != "Delete file" else None
        if action != "Delete file" and (not destination or target is None or not target.is_dir()):
            self._status = "Choose an existing destination folder before running the rule."
            self.changed.emit()
            return
        if not self._rule_plan:
            self._status = "Preview the rule and confirm that it has matching files before running it."
            self.changed.emit()
            return
        for row in self._rule_plan:
            source = Path(row["path"])
            policy = row["policy"] if row["conflict"] else self._rule_config.get("conflict_policy", "Keep both")
            try:
                if not source.is_file() or _is_reparse(os.lstat(source)) or not self._matches_rule(source, self._rule_conditions):
                    skipped += 1; continue
                if action == "Delete file":
                    send_to_recycle_bin(source); deleted += 1; continue
                requested = target / source.name
                if os.path.normcase(str(requested.resolve())) == os.path.normcase(str(source.resolve())):
                    skipped += 1; continue
                destination = requested
                if destination.exists():
                    if policy == "Skip": skipped += 1; continue
                    if policy == "Keep both": destination = unique_conflict_path(destination)
                destination.parent.mkdir(parents=True, exist_ok=True)
                if action == "Move file":
                    if policy == "Replace" and destination.exists(): move_with_replace(source, destination)
                    else: shutil.move(str(source), str(destination))
                    moved += 1
                else:
                    shutil.copy2(source, destination); copied += 1
            except (OSError, ValueError, KeyError): failed += 1
        self._status = f"Moved {moved:,} · copied {copied:,} · skipped {skipped:,} · sent to Recycle Bin {deleted:,} · failed {failed:,}."
        log_activity(self, f"Build rule: {action}", self._status)
        self._rule_plan = []; self._rows = []; self.changed.emit()

    @Slot(str)
    def navigate(self, page):
        self._page = page
        self._rows = []
        self._search_selected.clear()
        self._extension_rows = []
        self._categories = []
        self._selected_startup = {}
        self._status = "Ready"
        if page == "Startup Manager":
            self._startup_filter = "Startup apps"
            self._startup_summary = ""
            self._startup_entries = []
            self._selected_startup = {}
            self._categories = []
            self._rows = []
            self._status = "Ready · Select Rescan to read the current Windows startup settings."
        if page == "Junk Cleaner" and not self.junkBusy:
            self._junk_specs = []
            self._junk_candidates = []
            self._junk_issues = []
            self._junk_indices_by_category = {}
            self._junk_view_indices = []
            self._junk_current_category = None
            self._junk_page = 0
            self._candidate_selected.clear()
            self._category_flags = {}
        if page == "Recent Activity":
            try:
                import json
                entries = json.loads(self.settings.value("recent_activity", "[]"))
                self._rows = [{
                    "name": str(x.get("action", "Activity")),
                    "detail": _compact_activity_detail(x.get("action", "Activity"), x.get("details", "")),
                    "path": x.get("time", ""),
                } for x in entries[:30]]
            except Exception as e: self._status = str(e)
        elif page == "Read Me":
            try: self._status = resource_path("README.md").read_text(encoding="utf-8")
            except OSError: self._status = "The user guide is not available in this installation."
        self.changed.emit()

    @Slot(str, str)
    def scanStorage(self, root, fast="true"):
        path = Path(root)
        if not path.is_dir():
            self._storage_scanning = False
            self._status = "Choose a valid drive or folder."
            self.changed.emit()
            return
        self._storage_root = path
        self._storage_node = None
        self._storage_nodes_by_path = {}
        self._rows = []
        self._extension_rows = []
        self._storage_expanded = set()
        self._storage_selected = set()
        use_fast = str(fast).lower() == "true" and is_ntfs_path(path)
        self._storage_fast = use_fast
        self._storage_scanning = True
        self._status = f"Scanning {path}…"
        worker = StorageScanWorker(path, use_fast)
        worker.progress.connect(self._storage_progress)
        worker.scan_finished.connect(self._storage_done)
        self._storage_worker = worker
        worker.start(); self._workers.append(worker); self.changed.emit()

    @Slot(str, int, int)
    def _storage_progress(self, path, directories, files):
        self._status = f"Scanning {path} · {directories:,} folders · {files:,} files"
        self.changed.emit()

    def _storage_done(self, root, extensions, errors, directories):
        self._storage_node = root
        node_index = {}
        stack = [root]
        while stack:
            node = stack.pop()
            node_index[_norm_path(node.path)] = node
            stack.extend(node.children)
        self._storage_nodes_by_path = node_index
        root.name = str(root.path)
        self._storage_expanded = {_norm_path(root.path)} if root.children or root.files else set()
        self._start_storage_directory_load(root)
        flat = self._storage_flat_rows()
        ext = sorted(
            ((name, stats) for name, stats in extensions.items()
             if root.allocated and stats.allocated * 100 / root.allocated >= 1),
            key=lambda x: x[1].allocated, reverse=True,
        )
        self._rows = flat
        self._storage_scanning = False
        self._extension_rows = [{
            "name": extension,
            "type": "Other" if extension == "(No Extension)" else file_type(Path("sample" + extension)),
            "share": stat.allocated * 100 / root.allocated if root.allocated else 0,
            "size": format_bytes(stat.size),
            "allocated": format_bytes(stat.allocated),
            "files": stat.files,
        } for extension, stat in ext[:100]]
        self._status = f"Scanned {directories:,} folders and {root.files:,} files · {format_bytes(root.size)} logical · {format_bytes(root.allocated)} allocated · {errors:,} inaccessible."
        if self._storage_fast:
            self._status += " Fast NTFS enumeration was used."
        log_activity(self, "Storage scan", f"Scanned {root.path}: {directories:,} folders, {root.files:,} files.")
        self.changed.emit()

    def _storage_flat_rows(self):
        rows = []
        root = self._storage_node
        if root is None:
            return rows
        def selected_path(path):
            key = _norm_path(path)
            if key in self._storage_selected:
                return True
            return any(key != selected and _is_within(path, selected)
                       for selected in self._storage_selected)
        def append_node(node, depth, parent_allocated, is_root=False):
            path_key = _norm_path(node.path)
            percent = 100.0 if is_root else (node.allocated * 100 / parent_allocated if parent_allocated else 0.0)
            rows.append({"name": node.name, "size": format_bytes(node.size),
                         "allocated": format_bytes(node.allocated), "files": node.files,
                         "folders": node.folders, "share": percent,
                         "sizeBytes": int(node.size), "allocatedBytes": int(node.allocated),
                         "fileCount": int(node.files),
                         "path": str(node.path), "kind": "folder", "depth": depth,
                         "expanded": path_key in self._storage_expanded,
                         "selected": selected_path(node.path),
                         "canExpand": bool(node.children or node.files), "isRoot": is_root})
            if path_key not in self._storage_expanded:
                return
            for child in node.children:
                append_node(child, depth + 1, node.allocated)
            for entry in node.file_entries if node.files_loaded else []:
                share = entry.allocated * 100 / node.allocated if node.allocated else 0.0
                entry_key = _norm_path(entry.path)
                rows.append({"name": entry.name, "size": format_bytes(entry.size),
                             "allocated": format_bytes(entry.allocated), "files": 1,
                             "sizeBytes": int(entry.size), "allocatedBytes": int(entry.allocated),
                             "fileCount": 1,
                             "folders": 0, "share": share,
                             "path": str(entry.path), "kind": "file", "depth": depth + 1,
                             "expanded": False, "selected": selected_path(entry.path),
                             "canExpand": False, "isRoot": False})
        append_node(root, 0, root.allocated, True)
        return rows

    @Slot(str)
    def toggleStorageFolder(self, raw_path):
        target = _norm_path(raw_path)
        node = self._find_storage_node(raw_path)
        if node is None:
            return
        if target in self._storage_expanded:
            self._storage_expanded.remove(target)
        else:
            self._storage_expanded.add(target)
            if not node.files_loaded:
                self._start_storage_directory_load(node)
        self._rows = self._storage_flat_rows()
        self.changed.emit()

    def _start_storage_directory_load(self, node):
        key = _norm_path(node.path)
        if node.files_loaded or key in self._storage_file_workers:
            return
        worker = StorageDirectoryFilesWorker(node.path, self._storage_fast)
        worker.completed.connect(self._storage_directory_files_done)
        self._storage_file_workers[key] = worker
        self._workers.append(worker)
        worker.start()

    @Slot(str, object, str)
    def _storage_directory_files_done(self, raw_path, files, error_text):
        key = _norm_path(raw_path)
        self._storage_file_workers.pop(key, None)
        node = self._find_storage_node(raw_path)
        if node is not None:
            node.file_entries = files or []
            node.files_loaded = True
            self._storage_data_revision += 1
            if error_text:
                self._status = error_text
            if key in self._storage_expanded:
                self._rows = self._storage_flat_rows()
            self.changed.emit()

    @Slot(str, int, int, result='QVariantList')
    def storageTreemapChildren(self, raw_path, metric=0, sort_mode=0):
        node = self._find_storage_node(raw_path)
        if node is None:
            return []
        if not node.files_loaded:
            self._start_storage_directory_load(node)
        result = []
        for child in node.children:
            result.append({
                "name": child.name, "path": str(child.path), "kind": "folder",
                "size": format_bytes(child.size), "allocated": format_bytes(child.allocated),
                "sizeBytes": int(child.size), "allocatedBytes": int(child.allocated),
                "files": child.files, "fileCount": child.files, "folders": child.folders,
                "canExpand": bool(child.children or child.files),
            })
        if node.files_loaded:
            for entry in node.file_entries:
                result.append({
                    "name": entry.name, "path": str(entry.path), "kind": "file",
                    "size": format_bytes(entry.size), "allocated": format_bytes(entry.allocated),
                    "sizeBytes": int(entry.size), "allocatedBytes": int(entry.allocated),
                    "files": 1, "fileCount": 1, "folders": 0, "canExpand": False,
                })
        def metric_value(row):
            if metric == 1:
                return int(row["fileCount"])
            if metric == 2:
                return int(row["allocatedBytes"])
            return int(row["sizeBytes"])
        if sort_mode == 2:
            result.sort(key=lambda row: row["name"].casefold())
        else:
            result.sort(key=metric_value, reverse=(sort_mode != 1))
        max_tiles = 300
        if len(result) > max_tiles:
            tail = result[max_tiles - 1:]
            result = result[:max_tiles - 1]
            result.append({
                "name": f"Other items ({len(tail):,})", "path": "", "kind": "aggregate",
                "size": format_bytes(sum(int(row["sizeBytes"]) for row in tail)),
                "allocated": format_bytes(sum(int(row["allocatedBytes"]) for row in tail)),
                "sizeBytes": sum(int(row["sizeBytes"]) for row in tail),
                "allocatedBytes": sum(int(row["allocatedBytes"]) for row in tail),
                "files": sum(int(row["fileCount"]) for row in tail),
                "fileCount": sum(int(row["fileCount"]) for row in tail),
                "folders": 0, "canExpand": False,
            })
        return result

    def _find_storage_node(self, raw_path):
        return self._storage_nodes_by_path.get(_norm_path(raw_path))

    @Slot(str, bool)
    def setStorageSelected(self, raw_path, selected):
        node = self._find_storage_node(raw_path)
        if node is None:
            key = _norm_path(raw_path)
            if selected:
                self._storage_selected.add(key)
            else:
                self._storage_selected.discard(key)
        else:
            def apply_to_subtree(current):
                key = _norm_path(current.path)
                if selected:
                    self._storage_selected.add(key)
                else:
                    self._storage_selected.discard(key)
                for entry in current.file_entries if current.files_loaded else []:
                    entry_key = _norm_path(entry.path)
                    if selected:
                        self._storage_selected.add(entry_key)
                    else:
                        self._storage_selected.discard(entry_key)
                for child in current.children:
                    apply_to_subtree(child)
            apply_to_subtree(node)
        self._rows = self._storage_flat_rows()
        self.changed.emit()

    @Slot()
    def deleteStorageSelection(self):
        if self._storage_node is None:
            self._status = "Scan a drive or folder first."
            self.changed.emit(); return
        root_key = _norm_path(self._storage_node.path)
        targets = sorted((Path(p) for p in self._storage_selected if p != root_key), key=lambda p: len(p.parts))
        targets = [path for path in targets if not any(_is_within(path, ancestor) and path != ancestor for ancestor in targets)]
        if not targets:
            self._status = "Select one or more files or folders below the scanned root."
            self.changed.emit(); return
        self._pending_storage_delete = [str(path) for path in targets]
        names = "; ".join(str(path) for path in targets[:4])
        if len(targets) > 4: names += f"; and {len(targets) - 4} more"
        self.confirmationRequested.emit("Delete selected storage items?",
                                        f"Send {len(targets)} selected item(s) to the Windows Recycle Bin?\n\n{names}")

    @Slot(str, str, str, str, str, str, str, str, str, str, str, str, str, bool)
    def searchFiles(self, roots, name, extensions, category, minimum_value, maximum_value,
                    minimum_unit="MB", maximum_unit="MB",
                    exclusions="", created_start="", created_end="", modified_start="", modified_end="",
                    include_subfolders=True):
        if self._search_running:
            self._status = "A search is already running. Cancel it or wait for it to finish."
            self.changed.emit(); return
        locations = tuple(x.strip() for x in roots.split(";") if x.strip())
        if not locations: self._status = "Choose one or more drives or folders."; self.changed.emit(); return
        normalized = tuple(dict.fromkeys(("." + x.strip().lstrip(".")).casefold() for x in extensions.replace(";", ",").split(",") if x.strip()))
        categories = tuple(x.strip() for x in category.split(",") if x.strip() and x.strip() != "Any type")
        try:
            unit_multipliers = {"B": 1, "KB": 1024, "MB": 1024 ** 2, "GB": 1024 ** 3}
            minimum_multiplier = unit_multipliers.get(minimum_unit.strip().upper())
            maximum_multiplier = unit_multipliers.get(maximum_unit.strip().upper())
            if minimum_multiplier is None or maximum_multiplier is None:
                raise ValueError("Choose B, KB, MB, or GB for each size filter.")
            minimum_bytes = int(float(minimum_value) * minimum_multiplier) if minimum_value.strip() else None
            maximum_bytes = int(float(maximum_value) * maximum_multiplier) if maximum_value.strip() else None
            if minimum_bytes is not None and minimum_bytes < 0 or maximum_bytes is not None and maximum_bytes < 0:
                raise ValueError("File sizes cannot be negative.")
            if minimum_bytes is not None and maximum_bytes is not None and minimum_bytes > maximum_bytes:
                raise ValueError("Minimum size cannot be greater than maximum size.")
            def date_range(start_text, end_text, label):
                start = _parse_ui_date(start_text).timestamp() if start_text.strip() else None
                end = (( _parse_ui_date(end_text) + timedelta(days=1)).timestamp() - 0.001
                       if end_text.strip() else None)
                if start is not None and end is not None and end < start:
                    raise ValueError(f"The end date for {label} cannot be before the start date.")
                return start, end
            created_from, created_to = date_range(created_start, created_end, "created date")
            modified_from, modified_to = date_range(modified_start, modified_end, "modified date")
        except ValueError as error:
            self._status = str(error) if str(error) else "Enter valid numeric sizes and dates (MM-DD-YYYY)."
            self.changed.emit(); return
        excluded_paths = tuple(x.strip() for x in exclusions.split(";") if x.strip())
        criteria = SearchCriteria(locations, excluded_paths, name.strip(), normalized, categories,
                                  minimum_bytes, maximum_bytes, created_from, created_to,
                                  modified_from, modified_to, bool(include_subfolders))
        if not (criteria.name or criteria.extensions or criteria.categories
                or minimum_bytes is not None or maximum_bytes is not None
                or created_from is not None or created_to is not None
                or modified_from is not None or modified_to is not None):
            self._status = "Select at least one search filter, such as a name, file type, size, or date."
            self.changed.emit(); return
        self.settings.setValue("file_search_locations", list(criteria.roots))
        self.settings.setValue("file_search_exclusions", list(criteria.exclusions))
        self._search_cancel.clear()
        self._search_selected.clear()
        self._status = "Searching…"
        self._rows = []
        self._search_running = True
        self.changed.emit()
        worker = FileSearchWorker(criteria, self._search_cancel)
        worker.completed.connect(self._search_done); worker.failed.connect(self._search_failed)
        worker.start(); self._workers.append(worker)

    @Slot()
    def cancelSearch(self):
        if self._search_running:
            self._search_cancel.set()
            self._status = "Stopping the search…"
            self.changed.emit()

    @Slot(str)
    def _search_failed(self, message):
        self._search_running = False
        self._status = str(message)
        self.changed.emit()

    def _search_done(self, payload):
        self._search_running = False
        results = payload["results"]
        issues = payload["issues"]
        files = payload["scanned_files"]
        folders = payload["scanned_folders"]
        truncated = payload["truncated"]
        self._search_selected.clear()
        self._rows = [{"name": Path(x.path).name, "type": Path(x.path).suffix or "No extension",
                       "size": x.size, "sizeText": format_bytes(x.size),
                       "created": x.created, "createdText": datetime.fromtimestamp(x.created).strftime("%m-%d-%Y"),
                       "modified": x.modified, "modifiedText": datetime.fromtimestamp(x.modified).strftime("%m-%d-%Y"),
                       "path": x.path, "selected": False} for x in results]
        self._status = f"Found {len(results):,} · scanned {files:,} files and {folders:,} folders · {len(issues):,} inaccessible" + (" · result limit reached" if truncated else "")
        if payload.get("cancelled"):
            self._status += " · cancelled"
        log_activity(self, "File search", f"Found {len(results):,} items in {files:,} files and {folders:,} folders.")
        self.changed.emit()

    @Slot(str, bool)
    def setSearchResultSelected(self, raw_path, selected):
        path = str(raw_path)
        if not any(row.get("path") == path for row in self._rows):
            return
        if selected:
            self._search_selected.add(path)
        else:
            self._search_selected.discard(path)
        self._rows = [{**row, "selected": row.get("path") in self._search_selected} for row in self._rows]
        self.changed.emit()

    @Slot(bool)
    def selectAllSearchResults(self, selected):
        if selected:
            self._search_selected = {str(row["path"]) for row in self._rows if row.get("path")}
        else:
            self._search_selected.clear()
        self._rows = [{**row, "selected": row.get("path") in self._search_selected} for row in self._rows]
        self.changed.emit()

    @Slot()
    def deleteSearchSelection(self):
        targets = sorted(self._search_selected, key=str.casefold)
        if not targets:
            self._status = "Select one or more search results first."
            self.changed.emit()
            return
        self._pending_search_delete = targets
        names = "; ".join(Path(path).name for path in targets[:5])
        if len(targets) > 5:
            names += f"; and {len(targets) - 5} more"
        self.confirmationRequested.emit(
            "Delete selected search results?",
            f"Send {len(targets):,} selected file(s) to the Windows Recycle Bin?\n\n{names}")

    def _transfer_search_selection(self, destination_path, move):
        targets = sorted(self._search_selected, key=str.casefold)
        if not targets:
            self._status = "Select one or more search results first."
            self.changed.emit()
            return
        try:
            destination = Path(destination_path).expanduser().resolve(strict=True)
            if not destination.is_dir() or _is_reparse(os.lstat(destination)):
                raise ValueError("Choose a valid destination folder.")
        except (OSError, ValueError) as error:
            self._status = str(error) or "Choose a valid destination folder."
            self.changed.emit()
            return

        completed = skipped = failed = 0
        completed_paths = set()
        reserved: set[str] = set()
        for raw_path in targets:
            source = Path(raw_path)
            try:
                if not source.is_file() or _is_reparse(os.lstat(source)):
                    skipped += 1
                    continue
                requested = destination / source.name
                if os.path.normcase(str(requested.resolve(strict=False))) == os.path.normcase(str(source.resolve(strict=True))):
                    skipped += 1
                    continue
                target = unique_conflict_path(requested, reserved) if requested.exists() or os.path.normcase(str(requested)) in reserved else requested
                reserved.add(os.path.normcase(str(target)))
                if move:
                    shutil.move(str(source), str(target))
                    completed_paths.add(raw_path)
                else:
                    shutil.copy2(source, target)
                completed += 1
            except (OSError, ValueError):
                failed += 1

        self._search_selected.clear()
        if move and completed_paths:
            self._rows = [row for row in self._rows if row.get("path") not in completed_paths]
        else:
            self._rows = [{**row, "selected": False} for row in self._rows]
        verb = "Moved" if move else "Copied"
        self._status = f"{verb} {completed:,} · skipped {skipped:,} · failed {failed:,}."
        if completed:
            log_activity(self, f"File search {verb.lower()}", self._status)
        self.changed.emit()

    @Slot(str)
    def moveSearchSelection(self, destination_path):
        self._transfer_search_selection(destination_path, True)

    @Slot(str)
    def copySearchSelection(self, destination_path):
        self._transfer_search_selection(destination_path, False)

    @Slot()
    def scanJunk(self):
        if self.junkBusy:
            return
        self._junk_specs = []
        self._junk_candidates = []
        self._junk_issues = []
        self._junk_indices_by_category = {}
        self._junk_view_indices = []
        self._junk_current_category = None
        self._junk_page = 0
        self._candidate_selected.clear()
        self._category_flags = {}
        self._categories = []
        self._rows = []
        self._junk_scanning = True
        self._status = "Scanning configured cleanup locations…"; self.changed.emit()
        worker = JunkScanWorker()
        worker.completed.connect(self._junk_done); worker.failed.connect(self._junk_scan_failed)
        try:
            worker.start()
            self._workers.append(worker)
        except RuntimeError as error:
            self._junk_scanning = False
            self._status = f"Cleanup scan could not be started: {error}"
            self.changed.emit()

    @Slot(str)
    def _junk_scan_failed(self, error):
        self._junk_scanning = False
        self._status = f"Cleanup scan failed: {error}"
        self.changed.emit()

    def _junk_done(self, specs, candidates, issues):
        self._junk_scanning = False
        self._junk_specs, self._junk_candidates, self._junk_issues = specs, candidates, issues
        recommended_keys = {spec.key for spec in specs if spec.recommended}
        self._candidate_selected = {
            index for index, candidate in enumerate(candidates)
            if candidate.category in recommended_keys
        }
        self._junk_indices_by_category = defaultdict(list)
        for index, candidate in enumerate(candidates):
            self._junk_indices_by_category[candidate.category].append(index)
        self._junk_view_indices = []
        self._junk_current_category = None
        self._junk_page = 0
        counts = defaultdict(int); sizes = defaultdict(int)
        issue_counts = defaultdict(int)
        selected_counts = defaultdict(int)
        selected_sizes = defaultdict(int)
        for c in candidates: counts[c.category] += c.item_count; sizes[c.category] += c.size
        for index in self._candidate_selected:
            candidate = candidates[index]
            selected_counts[candidate.category] += candidate.item_count
            selected_sizes[candidate.category] += candidate.size
        for issue in issues: issue_counts[issue.category] += 1
        self._categories = [{"key": s.key, "name": s.label,
                             "detail": s.description,
                             "group": s.group, "recommended": s.recommended,
                             "itemCount": counts[s.key], "size": sizes[s.key],
                             "sizeText": format_bytes(sizes[s.key]),
                             "issueCount": issue_counts[s.key], "selectedCount": selected_counts[s.key],
                             "selectedSize": selected_sizes[s.key],
                             "selectedSizeText": format_bytes(selected_sizes[s.key]),
                             "checked": bool(counts[s.key]) and selected_counts[s.key] == counts[s.key], "expanded": False}
                            for s in specs]
        self._category_flags = {s.key: bool(counts[s.key]) and selected_counts[s.key] == counts[s.key] for s in specs}
        self._rows = []
        self._status = f"Found {len(candidates):,} cleanup candidates · {len(issues):,} scan issues. Recommended items are preselected; review them before cleaning."
        self.changed.emit()

    @Slot(str)
    def showJunkCategory(self, key):
        self.toggleJunkCategory(key)

    @Slot(str)
    def toggleJunkCategory(self, key):
        if key == "All":
            return
        if self._junk_current_category == key:
            self._junk_current_category = None
            self._junk_view_indices = []
            self._junk_page = 0
            self._rows = []
        else:
            self._junk_current_category = key
            self._junk_view_indices = list(self._junk_indices_by_category.get(key, ()))
            if self._junk_sort_field:
                field = self._junk_sort_field
                def value(index):
                    candidate = self._junk_candidates[index]
                    if field == "name": return Path(candidate.path).name.casefold() if candidate.path else candidate.category.casefold()
                    if field == "size": return candidate.size
                    if field == "modified": return candidate.modified_ns
                    if field == "itemStatus": return candidate.kind.casefold()
                    return candidate.path.casefold()
                self._junk_view_indices.sort(key=value, reverse=self._junk_sort_descending)
            self._junk_page = 0
            self._render_junk_page()
        self._categories = [{**category, "expanded": category["key"] == self._junk_current_category}
                            for category in self._categories]
        label = "all categories" if key == "All" else key
        self._status = f"Showing {len(self._junk_view_indices):,} items in {label} · {len(self._candidate_selected):,} selected."
        self.changed.emit()

    @Slot(str, bool)
    def sortJunkResults(self, field, descending):
        self._junk_sort_field = field
        self._junk_sort_descending = bool(descending)
        def value(index):
            candidate = self._junk_candidates[index]
            if field == "name": return Path(candidate.path).name.casefold() if candidate.path else candidate.category.casefold()
            if field == "size": return candidate.size
            if field == "modified": return candidate.modified_ns
            if field == "itemStatus": return candidate.kind.casefold()
            return candidate.path.casefold()
        self._junk_view_indices.sort(key=value, reverse=self._junk_sort_descending)
        self._junk_page = 0
        self._render_junk_page()
        self.changed.emit()

    @Slot(bool)
    def selectAllJunk(self, selected):
        if selected:
            self._candidate_selected = set(range(len(self._junk_candidates)))
            self._category_flags = {spec.key: bool(self._junk_indices_by_category.get(spec.key))
                                    for spec in self._junk_specs}
        else:
            self._candidate_selected.clear()
            self._category_flags = {spec.key: False for spec in self._junk_specs}
        self._sync_junk_selection()

    @Slot(int)
    def setJunkPage(self, page):
        page_count = max(1, (len(self._junk_view_indices) + self._junk_page_size - 1) // self._junk_page_size)
        self._junk_page = max(0, min(int(page), page_count - 1))
        self._render_junk_page()
        self.changed.emit()

    def _render_junk_page(self):
        start = self._junk_page * self._junk_page_size
        page_indices = self._junk_view_indices[start:start + self._junk_page_size]
        self._rows = [{"name": Path(candidate.path).name if candidate.path else candidate.category,
                       "detail": f"{candidate.category} · {format_bytes(candidate.size)} · {'folder' if candidate.is_directory else 'file'}",
                       "path": candidate.path, "candidateIndex": index,
                       "size": candidate.size,
                       "sizeText": format_bytes(candidate.size),
                       "modified": datetime.fromtimestamp(candidate.modified_ns / 1_000_000_000).strftime("%m-%d-%Y %H:%M") if candidate.modified_ns else "—",
                       "itemStatus": "Windows action" if candidate.kind in ("recycle_bin", "delivery_cache") else "Ready",
                       "selected": index in self._candidate_selected}
                      for index in page_indices
                      for candidate in (self._junk_candidates[index],)]

    @Slot(str, bool)
    def setCategorySelected(self, key, selected):
        self._category_flags[key] = selected
        indices = self._junk_indices_by_category.get(key, ())
        if selected: self._candidate_selected.update(indices)
        else: self._candidate_selected.difference_update(indices)
        self._sync_junk_selection()

    @Slot(str, bool)
    def setJunkGroupSelected(self, group, selected):
        keys = {spec.key for spec in self._junk_specs if spec.group == group}
        indices = {index for key in keys for index in self._junk_indices_by_category.get(key, ())}
        if selected:
            self._candidate_selected.update(indices)
        else:
            self._candidate_selected.difference_update(indices)
        for key in keys:
            category_indices = self._junk_indices_by_category.get(key, ())
            self._category_flags[key] = bool(category_indices) and all(
                candidate_index in self._candidate_selected for candidate_index in category_indices
            )
        self._sync_junk_selection()

    @Slot(int, bool)
    def setCandidateSelected(self, index, selected):
        if index < 0 or index >= len(self._junk_candidates):
            return
        category = self._junk_candidates[index].category
        if selected: self._candidate_selected.add(index)
        else: self._candidate_selected.discard(index)
        category_indices = self._junk_indices_by_category.get(category, ())
        self._category_flags[category] = bool(category_indices) and all(
            candidate_index in self._candidate_selected for candidate_index in category_indices
        )
        self._sync_junk_selection()

    def _sync_junk_selection(self):
        selected_count = len(self._candidate_selected)
        selected_item_counts = defaultdict(int)
        selected_sizes = defaultdict(int)
        for index in self._candidate_selected:
            candidate = self._junk_candidates[index]
            selected_item_counts[candidate.category] += candidate.item_count
            selected_sizes[candidate.category] += candidate.size
        self._categories = [{**x,
                             "checked": self._category_flags.get(x["key"], False),
                             "selectedCount": selected_item_counts.get(x["key"], 0),
                             "selectedSize": selected_sizes.get(x["key"], 0),
                             "selectedSizeText": format_bytes(selected_sizes.get(x["key"], 0))}
                            for x in self._categories]
        if self._junk_current_category is not None:
            self._render_junk_page()
        if self._junk_candidates:
            self._status = f"{len(self._junk_candidates):,} candidates · {selected_count:,} selected."
        self.changed.emit()

    @Slot()
    def cleanSelected(self):
        if self.junkBusy:
            self._status = "Wait for the current cleanup operation to finish."
            self.changed.emit()
            return
        candidates = [c for i, c in enumerate(self._junk_candidates) if i in self._candidate_selected]
        selected = {candidate.category for candidate in candidates}
        specs = [s for s in self._junk_specs if s.key in selected]
        if not candidates: self._status = "Select a cleanup category with candidates first."; self.changed.emit(); return
        counts = defaultdict(int); sizes = defaultdict(int)
        labels = {spec.key: spec.label for spec in specs}
        for candidate in candidates:
            counts[candidate.category] += candidate.item_count
            sizes[candidate.category] += candidate.size
        summary = "; ".join(f"{labels.get(key, key)}: {counts[key]:,} item(s), {format_bytes(sizes[key])}"
                             for key in sorted(counts))
        self._pending_junk_clean = (candidates, specs)
        self.confirmationRequested.emit(
            "Confirm cleanup",
            f"Selected cleanup actions: {summary}\n\nRegular files will be moved to the Recycle Bin where possible. This may not free disk space until the Recycle Bin is emptied.")

    def _start_junk_clean(self):
        if self.junkBusy:
            self._status = "Wait for the current cleanup operation to finish."
            self.changed.emit()
            return
        pending = self._pending_junk_clean
        self._pending_junk_clean = None
        if not pending:
            return
        candidates, specs = pending
        worker = JunkCleanWorker(candidates, specs)
        worker.completed.connect(self._clean_done)
        worker.failed.connect(self._junk_clean_failed)
        self._junk_cleaning = True
        self._status = f"Cleaning {len(candidates):,} selected items…"
        self.changed.emit()
        try:
            worker.start()
            self._workers.append(worker)
        except RuntimeError as error:
            self._junk_cleaning = False
            self._status = f"Cleanup could not be started: {error}"
            self.changed.emit()

    @Slot(str)
    def _junk_clean_failed(self, error):
        self._junk_cleaning = False
        self._status = f"Cleanup failed: {error}"
        self.changed.emit()

    def _clean_done(self, result):
        self._junk_cleaning = False
        self._candidate_selected.clear()
        self._category_flags = {spec.key: False for spec in self._junk_specs}
        self._categories = [{**category, "checked": False,
                             "selectedSize": 0, "selectedSizeText": format_bytes(0)}
                            for category in self._categories]
        self._rows = [{**row, "selected": False} for row in self._rows]
        def reason_label(reason, failed=False):
            reason = str(reason).casefold()
            if "in use" in reason or "exclusively" in reason: return "in use"
            if "protected" in reason: return "protected"
            if "changed" in reason or "replaced" in reason: return "changed since scan"
            if "symbolic" in reason or "reparse" in reason: return "link skipped"
            if "age rule" in reason or "newer than" in reason: return "does not meet age rule"
            if "empty" in reason or "file rule" in reason: return "no longer eligible"
            if "approved location" in reason or "inside its approved" in reason: return "location is no longer eligible"
            if "permission" in reason or "access denied" in reason: return "access denied"
            return "operation error" if failed else "could not safely revalidate"
        def summarize(entries, failed=False):
            reasons = defaultdict(int)
            for _path, reason in entries: reasons[reason_label(reason, failed)] += 1
            return ", ".join(f"{label.title()}: {count}" for label, count in sorted(reasons.items(), key=lambda item: (-item[1], item[0]))) or "none"
        skipped_count, failed_count = len(result["skipped"]), len(result["failed"])
        details = (f"Moved to Recycle Bin: {result['moved']:,} item(s), {format_bytes(result['moved_bytes'])}.\n"
                   f"Measured disk space freed: {format_bytes(result['freed_bytes'])}.\n"
                   f"Skipped after revalidation: {skipped_count:,}" + (f" (Reason: {summarize(result['skipped'])})" if skipped_count else "") + ".\n"
                   f"Failed: {failed_count:,}" + (f" (Reason: {summarize(result['failed'], failed=True)})" if failed_count else "") + ".")
        if result.get("recycle_emptied"):
            details += "\nRecycle Bin emptied after its separate warning."
        if result.get("recycle_error"):
            details += "\nRecycle Bin cleanup failed: " + result["recycle_error"]
        if result.get("delivery_cleaned"):
            details += "\nDelivery Optimization cleanup completed through Windows."
        if result.get("delivery_error"):
            details += "\nDelivery Optimization cleanup failed: " + result["delivery_error"]
        self._status = f"Cleanup complete · moved {result['moved']:,} · skipped {skipped_count:,} · failed {failed_count:,}."
        log_activity(self, "Junk cleanup", details)
        self.cleanupCompleted.emit(details)
        self.changed.emit()

    @Slot()
    def scanStartup(self):
        if self._startup_scanning:
            return
        self._startup_scanning = True
        self._startup_filter = "Startup apps"
        self._startup_entries = []
        self._selected_startup = {}
        self._categories = []
        self._rows = []
        self._status = "Scanning startup apps, tasks, services, approvals, and policies…"
        self.changed.emit()
        worker = AutorunScanWorker(self.settings)
        worker.completed.connect(self._startup_done)
        worker.failed.connect(self._startup_failed)
        try:
            worker.start()
            self._workers.append(worker)
        except RuntimeError as error:
            self._startup_scanning = False
            self._status = f"Startup scan could not be started: {error}"
            self.changed.emit()

    @Slot(str)
    def _startup_failed(self, error):
        self._startup_scanning = False
        if self._page == "Startup Manager":
            self._status = f"Startup scan failed: {error}"
        self.changed.emit()

    @staticmethod
    def _startup_row(entry):
        display_status = ("Disabled" if entry.category == "Startup apps"
                          and entry.metadata.get("approval_status") == "Disabled"
                          else entry.status)
        return {
            "name": entry.name,
            "category": entry.category,
            "detail": f"{entry.publisher} · {display_status} · {entry.impact}",
            "publisher": entry.publisher or "Unknown",
            "source": entry.source or "Unknown",
            "status": display_status,
            "enabledAction": entry.controllable and display_status == "Disabled" and entry.category != "Services",
            "disabledAction": entry.controllable and display_status == "Enabled" and entry.category != "Services",
            "impact": entry.impact,
            "duplicate": "Yes" if entry.duplicate else "No",
            "executable": entry.executable or "—",
            "location": entry.location or "—",
            "command": entry.command or "—",
            "arguments": entry.arguments or "—",
            "path": entry.executable or entry.location,
            "entryId": entry.entry_id,
        }

    @Slot(str, result=str)
    def startupIcon(self, entry_id):
        entry = next((item for item in self._startup_entries if item.entry_id == str(entry_id)), None)
        return _startup_icon_data(entry.executable) if entry else ""

    def _startup_done(self, entries, version, architecture, errors):
        self._startup_scanning = False
        if self._page != "Startup Manager":
            self.changed.emit()
            return
        self._startup_entries = entries
        self._categories = [
            {"key": category, "name": category,
             "detail": str(sum(1 for item in entries if item.category.casefold() == category.casefold())),
             "label": f"{category} ({sum(1 for item in entries if item.category.casefold() == category.casefold())})",
             "checked": category == self._startup_filter}
            for category in TAB_CATEGORIES
        ]
        visible_entries = [entry for entry in entries
                           if entry.category.casefold() == self._startup_filter.casefold()]
        self._rows = [self._startup_row(entry) for entry in visible_entries]
        self._startup_summary = f"{version} · {architecture} · {len(entries):,} entries · {len(errors):,} scan notices."
        self._status = self._startup_summary
        self.changed.emit()

    @Slot(str)
    def filterStartup(self, category):
        self._startup_filter = category
        self._selected_startup = {}
        values = (self._startup_entries if category == "All" else
                  [entry for entry in self._startup_entries if entry.category.casefold() == category.casefold()])
        self._rows = [self._startup_row(entry) for entry in values]
        self._categories = [{**item, "checked": item["key"] == category} for item in self._categories]
        self._status = self._startup_summary or f"{len(values):,} {category.lower()} entries."
        self.changed.emit()

    @Slot(str)
    def selectStartup(self, entry_id):
        entry = next((item for item in self._startup_entries if item.entry_id == entry_id), None)
        if not entry: return
        self._selected_startup = {
            "entryId": entry.entry_id, "name": entry.name, "source": entry.source,
            "location": entry.location, "command": entry.command or "—",
            "executable": entry.executable or "Unknown", "arguments": entry.arguments or "—",
            "status": entry.status, "category": entry.category,
            "displayStatus": ("Disabled" if entry.category == "Startup apps"
                              and entry.metadata.get("approval_status") == "Disabled"
                              else entry.status),
            "stateNote": ("This Run or Startup folder entry is present, but Windows marks its Startup Approved state as disabled."
                          if entry.category == "Startup apps"
                          and entry.metadata.get("approval_status") == "Disabled" else ""),
            "publisher": entry.publisher, "signature": entry.signature,
            "fileExists": entry.file_exists, "safety": entry.safety,
            "impact": entry.impact, "duplicate": entry.duplicate,
            "enabledAction": entry.controllable and ("Disabled" if entry.category == "Startup apps"
                                                       and entry.metadata.get("approval_status") == "Disabled"
                                                       else entry.status) == "Disabled" and entry.category != "Services",
            "disabledAction": entry.controllable and ("Disabled" if entry.category == "Startup apps"
                                                        and entry.metadata.get("approval_status") == "Disabled"
                                                        else entry.status) == "Enabled" and entry.category != "Services",
            "serviceEnableAction": entry.controllable and entry.category == "Services" and entry.status == "Disabled",
            "serviceDisableAction": entry.controllable and not entry.protected and entry.category == "Services" and entry.status == "Enabled",
        }
        self.changed.emit()

    @Slot()
    def clearStartupSelection(self):
        self._selected_startup = {}
        self.changed.emit()

    @Slot(str, bool)
    def startupAction(self, entry_id, enable):
        self._startup_action_notice = ""
        entry = next((item for item in self._startup_entries if item.entry_id == entry_id), None)
        if not entry: self._status = "Select a startup entry first."; self.changed.emit(); return
        if entry.category == "Services": self._status = "Service changes require the separate advanced service confirmation."; self.changed.emit(); return
        try:
            self._apply_startup_change(entry, enable)
        except StartupConfirmationRequired as confirmation:
            self._pending_confirmation = ("startup", entry_id, enable)
            self.confirmationRequested.emit(confirmation.title, confirmation.message)
        except Exception as error:
            self._startup_action_notice = self._startup_action_error_message(error, entry)
            self._status = self._startup_action_notice
            self.changed.emit()
            self.startupActionFailed.emit(self._startup_action_notice)

    @staticmethod
    def _startup_action_error_message(error, entry=None):
        detail = str(error).strip()
        lowered = detail.casefold()
        denied = (isinstance(error, PermissionError)
                  or getattr(error, "winerror", None) == 5
                  or any(marker in lowered for marker in (
                      "access is denied", "permission denied", "access denied",
                      "requires elevation", "elevation required", "administrator privileges")))
        if denied:
            item_name = str(getattr(entry, "name", "startup item") or "startup item")
            return (f"The startup setting for {item_name} requires administrator privileges to change. "
                    "Close FileSense, reopen it by right-clicking the app and choosing "
                    "‘Run as administrator’, then try again.")
        return f"Could not update this startup item: {detail or 'an unknown error occurred.'}"

    @Slot(str, bool)
    def serviceAction(self, entry_id, enable):
        self._startup_action_notice = ""
        entry = next((item for item in self._startup_entries if item.entry_id == entry_id), None)
        if not entry or entry.category != "Services": return
        message = ("Enable" if enable else "Disable") + f" automatic startup for {entry.name}? Changing services can affect Windows or installed software."
        self._pending_confirmation = ("service", entry_id, enable)
        self.confirmationRequested.emit("Advanced service change", message)

    def _apply_startup_change(self, entry, enable, confirmed=False, advanced_service=False):
        target = entry
        if entry.category == "Startup apps":
            approval_id = entry.metadata.get("approval_entry_id")
            if approval_id:
                target = next((item for item in self._startup_entries if item.entry_id == approval_id), entry)
        try:
            _set_enabled(target, enable, self.settings, None, advanced_service=advanced_service,
                         qml_mode=True, confirmed=confirmed)
            new_status = "Enabled" if enable else "Disabled"
            target.status = new_status
            if target.category == "Startup Approved":
                for linked in self._startup_entries:
                    if linked.category == "Startup apps" and linked.metadata.get("approval_entry_id") == target.entry_id:
                        linked.status = new_status
                        linked.metadata["approval_status"] = new_status
            elif entry.category == "Startup apps":
                entry.status = new_status
                entry.metadata["approval_status"] = "Unknown"
            self._refresh_startup_rows()
            self._startup_action_notice = ""
            action = "Autorun: Service " if advanced_service else "Autorun: "
            verb = ("restore" if enable else "disable") if advanced_service else ("Enable / restore" if enable else "Disable")
            log_activity(self, action + verb, f"{entry.name}; {entry.source}; {entry.location}; {entry.command or entry.executable}")
            self._status = "Startup item enabled." if enable else "Startup item disabled."
            if self._selected_startup.get("entryId"):
                self.selectStartup(self._selected_startup["entryId"])
            else:
                self.changed.emit()
        except StartupConfirmationRequired:
            raise
        except Exception as error:
            self._startup_action_notice = self._startup_action_error_message(error, entry)
            self._status = self._startup_action_notice
            self.changed.emit()
            self.startupActionFailed.emit(self._startup_action_notice)

    def _refresh_startup_rows(self):
        values = (self._startup_entries if self._startup_filter == "All" else
                  [item for item in self._startup_entries
                   if item.category.casefold() == self._startup_filter.casefold()])
        self._rows = [self._startup_row(item) for item in values]

    @Slot(bool)
    def respondToConfirmation(self, accepted):
        pending = self._pending_confirmation
        self._pending_confirmation = None
        search_targets = getattr(self, "_pending_search_delete", [])
        if search_targets:
            self._pending_search_delete = []
            if not accepted:
                return
            deleted = skipped = failed = 0
            removed_paths = set()
            for raw in search_targets:
                path = Path(raw)
                try:
                    if not path.is_file() or _is_reparse(os.lstat(path)):
                        skipped += 1
                        if not path.exists():
                            removed_paths.add(raw)
                        continue
                    send_to_recycle_bin(path)
                    deleted += 1
                    removed_paths.add(raw)
                except (OSError, AttributeError):
                    failed += 1
            self._search_selected.clear()
            self._rows = [{**row, "selected": False} for row in self._rows if row.get("path") not in removed_paths]
            self._status = f"Sent {deleted:,} selected file(s) to the Recycle Bin · skipped {skipped:,} · failed {failed:,}."
            if deleted:
                log_activity(self, "File search delete", self._status)
            self.changed.emit()
            return
        storage_targets = getattr(self, "_pending_storage_delete", [])
        if storage_targets:
            self._pending_storage_delete = []
            if not accepted:
                return
            deleted = failed = 0
            for raw in storage_targets:
                path = Path(raw)
                try:
                    if not path.exists() or _is_reparse(os.lstat(path)):
                        failed += 1
                        continue
                    send_to_recycle_bin(path)
                    deleted += 1
                except (OSError, AttributeError):
                    failed += 1
            self._storage_selected.clear()
            log_activity(self, "Storage delete", f"Sent {deleted} item(s) to Recycle Bin; failed {failed}.")
            if self._storage_root and self._storage_root.is_dir():
                self._status = f"Sent {deleted} item(s) to Recycle Bin · failed {failed}. Refreshing storage scan…"
                self.scanStorage(str(self._storage_root), "true" if self._storage_fast else "false")
            else:
                self._status = f"Sent {deleted} item(s) to Recycle Bin · failed {failed}."
                self.changed.emit()
            return
        if self._pending_junk_clean:
            if not accepted:
                self._pending_junk_clean = None
                self._pending_junk_recycle_confirmation = False
                return
            candidates, _specs = self._pending_junk_clean
            includes_recycle = any(candidate.kind == "recycle_bin" for candidate in candidates)
            if includes_recycle and not self._pending_junk_recycle_confirmation:
                self._pending_junk_recycle_confirmation = True
                self.confirmationRequested.emit(
                    "Permanently empty the Recycle Bin?",
                    "This permanently removes the items already in the Recycle Bin and removes their normal recovery option. Continue?")
                return
            self._pending_junk_recycle_confirmation = False
            self._start_junk_clean()
            return
        if not accepted or not pending:
            return
        kind, entry_id, enable = pending
        entry = next((item for item in self._startup_entries if item.entry_id == entry_id), None)
        if not entry:
            self._status = "The startup entry is no longer available. Refresh the scan."
            self.changed.emit()
            return
        self._apply_startup_change(entry, enable, confirmed=True, advanced_service=(kind == "service"))

    @Slot(str)
    def quickScan(self, kind):
        self.quickScanAt(str(Path.home()), kind)

    @Slot(str, str, bool)
    @Slot(str, str, bool, 'QVariantList')
    @Slot(str, str, bool, 'QVariantList', 'QVariantList')
    def quickScanAt(self, root, kind, include_subfolders=True, conditions=None, excluded_paths=None):
        roots = tuple(x.strip() for x in str(root).split(";") if x.strip())
        if not roots or not any(Path(value).is_dir() for value in roots): self._status = "Choose a valid folder to scan."; self.changed.emit(); return
        condition_keys = ("logic", "field", "operator", "typeValue", "value")
        normalized_conditions = []
        for condition in conditions or ():
            if isinstance(condition, dict):
                normalized_conditions.append(condition)
                continue
            if hasattr(condition, "toVariant"):
                converted = condition.toVariant()
                if isinstance(converted, dict):
                    normalized_conditions.append(converted)
                    continue
            if hasattr(condition, "property"):
                normalized_conditions.append({key: condition.property(key) for key in condition_keys})
            else:
                normalized_conditions.append({})
        conditions = normalized_conditions
        if kind == "duplicates" and conditions:
            for condition in conditions:
                if condition.get("field") == "File Type" and not condition.get("typeValue", "").strip():
                    self._status = "Choose a file type for every File Type condition."; self.changed.emit(); return
                if condition.get("field") == "File Extension" and not condition.get("value", "").strip():
                    self._status = "Enter an extension for every File Extension condition."; self.changed.emit(); return
        worker = QuickDiscoveryWorker(kind, Path(roots[0]), conditions)
        worker.root = ";".join(roots)
        worker.include_subfolders = include_subfolders
        worker.excluded_paths = excluded_paths or []
        worker.completed.connect(self._quick_done)
        self._workers.append(worker)
        self._quick_kind = kind
        self._status = f"Searching {len(roots)} selected folder(s) for {kind}…"; self.changed.emit()
        worker.start()

    @staticmethod
    def _matches_duplicate_rule(path, conditions):
        outcomes = []
        for condition in conditions:
            field = condition.get("field", "File Type")
            operator = condition.get("operator", "Is")
            expected = str(condition.get("typeValue", "") if field == "File Type" else condition.get("value", "")).strip().casefold()
            if field == "File Type":
                actual = file_type(path).casefold()
                matched = {"Is": actual == expected, "Is not": actual != expected,
                           "Contains": expected in actual, "Does not contain": expected not in actual}[operator]
            else:
                actual = path.name.casefold()
                if not expected.startswith("."):
                    expected = "." + expected
                matched = {"Is": actual.endswith(expected), "Is not": not actual.endswith(expected),
                           "Contains": expected in actual, "Does not contain": expected not in actual}[operator]
            outcomes.append(matched)
        if not outcomes:
            return True
        result = outcomes[0]
        for index in range(1, len(outcomes)):
            logic = conditions[index].get("logic", "AND")
            if logic == "AND":
                result = result and outcomes[index]
            elif logic == "OR":
                result = result or outcomes[index]
            else:
                result = result and not outcomes[index]
        return result

    def _quick_done(self, rows, error):
        self._duplicate_groups = defaultdict(list)
        self._duplicate_delete_selected = {}
        self._rows = []
        group_sizes = defaultdict(set)
        for size, path, group, item_type in rows:
            if group and item_type == "File":
                group_sizes[group].add(size)
        for size, path, group, item_type in rows:
            if group:
                self._duplicate_groups[group].append(str(path))
                self._duplicate_delete_selected[str(path)] = False
            comparison = "—"
            if group and item_type == "File":
                comparison = "Same size" if len(group_sizes[group]) == 1 else "Different sizes"
            self._rows.append({"name": path.name, "detail": f"{item_type} · {format_bytes(size)}" + (f" · duplicate group {group}" if group else ""), "path": str(path), "duplicateGroup": group, "deleteSelected": False, "fileType": item_type, "size": size, "sizeText": format_bytes(size) if item_type == "File" else "—", "sizeComparison": comparison})
        groups_found = len(self._duplicate_groups)
        if getattr(self, "_quick_kind", "duplicates") == "duplicates":
            issue_note = " · scan notices" if error else ""
            self._status = f"Found {groups_found:,} duplicate-name group(s), {len(rows):,} entries{issue_note}."
            if error: self._status += " " + error
            log_activity(self, "Duplicate scan", f"Found {groups_found:,} duplicate-name group(s), {len(rows):,} entries{issue_note}.")
        else:
            self._status = f"Found {len(rows):,} matching files." + (f" Scan notices: {error}" if error else "")
        self.changed.emit()

    @Slot(str, bool)
    def setDuplicateDeleteSelected(self, path, selected):
        self._duplicate_delete_selected[path] = selected
        self._rows = [{**row, "deleteSelected": selected if row.get("path") == path else row.get("deleteSelected", False)} for row in self._rows]
        self.changed.emit()

    @Slot()
    def resolveDuplicates(self):
        removed = 0; skipped = 0; failed = 0
        keepers = {path for group, paths in self._duplicate_groups.items()
                   for path in paths if not self._duplicate_delete_selected.get(path, False)}
        to_remove_all = [Path(path) for paths in self._duplicate_groups.values() for path in paths
                         if self._duplicate_delete_selected.get(path, False)]
        if any(source.is_dir() and any(source != Path(keeper) and source in Path(keeper).parents
                                       for keeper in keepers) for source in to_remove_all):
            self._status = "Review folder choices: a folder marked for deletion contains an unchecked entry that would be kept. Mark the nested entry for deletion or uncheck the folder."
            self.changed.emit()
            return
        for group, paths in self._duplicate_groups.items():
            to_remove = [path for path in paths if self._duplicate_delete_selected.get(path, False)]
            for raw in to_remove:
                path = Path(raw)
                try:
                    if not path.exists() or _is_reparse(os.lstat(path)): skipped += 1; continue
                    send_to_recycle_bin(path)
                    removed += 1
                except (OSError, PermissionError): failed += 1
        self._rows = [row for row in self._rows if Path(row["path"]).exists()]
        noun = "entry" if removed == 1 else "entries"
        self._status = f"Sent {removed:,} checked {noun} to the Recycle Bin; kept unchecked entries · skipped {skipped:,} · failed {failed:,}."
        if removed: log_activity(self, "Duplicate cleanup", self._status)
        self.changed.emit()

    @Slot(str)
    def openLocation(self, path):
        p = Path(path)
        target = p if p.is_dir() else p.parent
        if target.exists(): QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))

    @Slot(str)
    def _set_status(self, status):
        self._status = str(status); self.changed.emit()
