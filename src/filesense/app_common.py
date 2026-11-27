"""FileSense. Fluent Qt desktop interface for Windows."""

from __future__ import annotations

import ctypes
import errno
import fnmatch
import json
import os
import queue
import shutil
import sys
import threading
import uuid
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from PySide6.QtCore import Qt, QDate, QItemSelectionModel, QPoint, QRectF, QSize, QSettings, QStorageInfo, QThread, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QPainter, QPalette, QPixmap
if os.environ.get("FILESENSE_QML_RUNTIME") == "1":
    class _WidgetsUiOnly:
        pass

    (QAbstractItemView, QApplication, QtCheckBox, QDateEdit, QDialog, QFileDialog, QFrame,
     QHBoxLayout, QHeaderView, QSizePolicy, QFileIconProvider, QLabel, QListWidget,
     QMessageBox, QProgressBar, QPushButton, QScrollArea, QSpinBox, QSplitter, QStyle,
     QStyleOptionButton, QTableWidgetItem, QTreeWidget, QTreeWidgetItem, QVBoxLayout,
     QWidget, BodyLabel, CaptionLabel, CardWidget, FluentCheckBox, ComboBox, FluentIcon,
     FluentWindow, LineEdit, PrimaryPushButton, PushButton, StrongBodyLabel,
     MenuAnimationType, NavigationItemPosition, SubtitleLabel, TableWidget,
     TabCloseButtonDisplayMode, TabWidget, TitleLabel, ToolButton, setTheme,
     setThemeColor, Theme, FluentIconBase, CheckBoxIcon) = (_WidgetsUiOnly,) * 50
    Theme.AUTO = None
else:
    from PySide6.QtWidgets import (
        QAbstractItemView, QApplication, QCheckBox as QtCheckBox, QDateEdit, QDialog, QFileDialog, QFrame, QHBoxLayout, QHeaderView, QSizePolicy,
        QFileIconProvider, QLabel, QListWidget, QMessageBox, QProgressBar, QPushButton,
        QScrollArea, QSpinBox, QSplitter, QStyle, QStyleOptionButton, QTableWidgetItem, QTreeWidget, QTreeWidgetItem,
        QVBoxLayout, QWidget,
    )
    from qfluentwidgets import (
        BodyLabel, CaptionLabel, CardWidget, CheckBox as FluentCheckBox, ComboBox, FluentIcon,
        FluentWindow, LineEdit, PrimaryPushButton, PushButton, StrongBodyLabel,
        MenuAnimationType, NavigationItemPosition, SubtitleLabel, TableWidget, TabCloseButtonDisplayMode, TabWidget, TitleLabel,
        ToolButton, setTheme, setThemeColor, Theme,
    )
    from qfluentwidgets.common.icon import FluentIconBase
    from qfluentwidgets.components.widgets.check_box import CheckBoxIcon


ACCENT_COLOR = "#147F78"


class CheckBox(FluentCheckBox):
    """Shared Fluent checkbox with a compact, consistently sized indicator."""

    INDICATOR_SIZE = 16

    def paintEvent(self, event) -> None:
        # Let Qt draw the label and control background, then paint Fluent's
        # indicator at a fixed size instead of the larger style-derived size.
        QtCheckBox.paintEvent(self, event)
        painter = QPainter(self)
        painter.setRenderHints(QPainter.RenderHint.Antialiasing)
        option = QStyleOptionButton()
        option.initFrom(self)
        rect = self.style().subElementRect(QStyle.SubElement.SE_CheckBoxIndicator, option, self)
        indicator_center = rect.center()
        rect.setWidth(self.INDICATOR_SIZE)
        rect.setHeight(self.INDICATOR_SIZE)
        rect.moveCenter(indicator_center)
        painter.setPen(self._borderColor())
        painter.setBrush(self._backgroundColor())
        painter.drawRoundedRect(rect, 4, 4)
        if not self.isEnabled():
            painter.setOpacity(0.8)
        if self.checkState() == Qt.CheckState.Checked:
            CheckBoxIcon.ACCEPT.render(painter, rect)
        elif self.checkState() == Qt.CheckState.PartiallyChecked:
            CheckBoxIcon.PARTIAL_ACCEPT.render(painter, rect)


CATEGORIES: dict[str, set[str]] = {
    "Compressed": {".zip", ".7z", ".rar", ".tar", ".gz", ".bz2", ".xz", ".tgz", ".cab", ".iso"},
    "Video": {".mp4", ".m4v", ".mkv", ".mov", ".avi", ".wmv", ".webm", ".flv", ".mpg", ".mpeg", ".3gp", ".ts"},
    "Audio": {".mp3", ".m4a", ".aac", ".wav", ".flac", ".ogg", ".opus", ".wma", ".aiff", ".mid", ".midi"},
    "Images": {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tif", ".tiff", ".webp", ".svg", ".heic", ".heif", ".avif", ".ico", ".raw", ".cr2", ".nef", ".arw"},
    "Documents": {".pdf", ".doc", ".docx", ".odt", ".rtf", ".txt", ".md", ".pages", ".xls", ".xlsx", ".ods", ".csv", ".ppt", ".pptx", ".odp", ".epub"},
    "Programs": {".exe", ".msi", ".msix", ".appx", ".appxbundle", ".bat", ".cmd", ".ps1", ".com", ".scr", ".jar", ".py", ".msu"},
}
DUPLICATES_FOLDER = "_Duplicates"
TYPE_OPERATORS = ("Is", "Is not", "Contains", "Does not contain")
SIZE_OPERATORS = ("Is", "Is not", "Greater than", "Less than", "At least", "At most")
NAME_OPERATORS = ("Contains", "Does not contain", "Starts with", "Ends with", "Matches exact text", "Matches pattern (advanced)")
DATE_OPERATORS = ("Before", "After", "Between", "Within last", "Older than", "Newer than")
SIZE_UNITS = {"B": 1, "KB": 1024, "MB": 1024**2, "GB": 1024**3}
CONFLICT_POLICIES = ("Skip", "Keep both", "Replace")


def resource_path(relative_path: str) -> Path:
    source_root = Path(__file__).resolve().parents[2]
    bundle_root = Path(getattr(sys, "_MEIPASS", source_root))
    return bundle_root / relative_path


def collision_safe_path(destination: Path, is_file: bool = False) -> Path:
    if not destination.exists():
        return destination
    index = 1
    while True:
        candidate = (destination.with_name(f"{destination.stem} ({index}){destination.suffix}")
                     if is_file and destination.suffix else destination.with_name(f"{destination.name} ({index})"))
        if not candidate.exists():
            return candidate
        index += 1


def unique_conflict_path(destination: Path, reserved: set[str] | None = None) -> Path:
    """Return a unique incoming-file name while preserving the existing file."""
    reserved = reserved or set()
    stem, suffix = destination.stem, destination.suffix
    index = 0
    while True:
        marker = f" ({index + 1})"
        candidate = destination.with_name(f"{stem}{marker}{suffix}")
        key = os.path.normcase(str(candidate))
        if not candidate.exists() and key not in reserved:
            return candidate
        index += 1


def move_with_replace(source: Path, destination: Path) -> None:
    """Move a file while replacing an existing destination only when requested."""
    try:
        os.replace(source, destination)
    except OSError as error:
        if error.errno != errno.EXDEV:
            raise
        shutil.copy2(source, destination)
        source.unlink()


def file_type(path: Path) -> str:
    extension = path.suffix.casefold()
    return next((category for category, extensions in CATEGORIES.items() if extension in extensions), "Other")


def format_file_size(path: Path) -> str:
    size = path.stat().st_size
    units = ("B", "KB", "MB", "GB", "TB")
    value = float(size)
    unit_index = 0
    while value >= 1024 and unit_index < len(units) - 1:
        value /= 1024
        unit_index += 1
    return f"{size:,} B" if unit_index == 0 else f"{value:.2f} {units[unit_index]} ({size:,} B)"


def format_bytes(size: int) -> str:
    units = ("B", "KB", "MB", "GB", "TB", "PB")
    value = float(size)
    unit_index = 0
    while value >= 1024 and unit_index < len(units) - 1:
        value /= 1024
        unit_index += 1
    return f"{size:,} B" if unit_index == 0 else f"{value:.1f} {units[unit_index]}"


if os.name == "nt":
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _get_compressed_file_size = _kernel32.GetCompressedFileSizeW
    _get_compressed_file_size.argtypes = [ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_uint32)]
    _get_compressed_file_size.restype = ctypes.c_uint32
    _get_disk_free_space = _kernel32.GetDiskFreeSpaceW
    _get_disk_free_space.argtypes = [
        ctypes.c_wchar_p,
        ctypes.POINTER(ctypes.c_uint32),
        ctypes.POINTER(ctypes.c_uint32),
        ctypes.POINTER(ctypes.c_uint32),
        ctypes.POINTER(ctypes.c_uint32),
    ]
    _get_disk_free_space.restype = ctypes.c_int

    class _FILETIME(ctypes.Structure):
        _fields_ = [("dwLowDateTime", ctypes.c_uint32), ("dwHighDateTime", ctypes.c_uint32)]

    class _WIN32_FIND_DATAW(ctypes.Structure):
        _fields_ = [
            ("dwFileAttributes", ctypes.c_uint32),
            ("ftCreationTime", _FILETIME),
            ("ftLastAccessTime", _FILETIME),
            ("ftLastWriteTime", _FILETIME),
            ("nFileSizeHigh", ctypes.c_uint32),
            ("nFileSizeLow", ctypes.c_uint32),
            ("dwReserved0", ctypes.c_uint32),
            ("dwReserved1", ctypes.c_uint32),
            ("cFileName", ctypes.c_wchar * 260),
            ("cAlternateFileName", ctypes.c_wchar * 14),
        ]

    _find_first_file_ex = _kernel32.FindFirstFileExW
    _find_first_file_ex.argtypes = [ctypes.c_wchar_p, ctypes.c_int, ctypes.POINTER(_WIN32_FIND_DATAW),
                                    ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32]
    _find_first_file_ex.restype = ctypes.c_void_p
    _find_next_file = _kernel32.FindNextFileW
    _find_next_file.argtypes = [ctypes.c_void_p, ctypes.POINTER(_WIN32_FIND_DATAW)]
    _find_next_file.restype = ctypes.c_int
    _find_close = _kernel32.FindClose
    _find_close.argtypes = [ctypes.c_void_p]
    _find_close.restype = ctypes.c_int
    _get_volume_information = _kernel32.GetVolumeInformationW
    _get_volume_information.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint32,
                                        ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                                        ctypes.c_wchar_p, ctypes.c_uint32]
    _get_volume_information.restype = ctypes.c_int
else:
    _get_compressed_file_size = None
    _get_disk_free_space = None
    _find_first_file_ex = _find_next_file = _find_close = _get_volume_information = None


def is_ntfs_path(path: Path) -> bool:
    if _get_volume_information is None:
        return False
    filesystem = ctypes.create_unicode_buffer(32)
    volume_root = path.anchor or str(path)
    return bool(_get_volume_information(volume_root, None, 0, None, None, None, filesystem, len(filesystem))
                and filesystem.value.casefold() == "ntfs")


def fast_windows_entries(directory: Path):
    """Enumerate directory entries using Win32's batched large-fetch mode."""
    data = _WIN32_FIND_DATAW()
    handle = _find_first_file_ex(str(directory / "*"), 1, ctypes.byref(data), 0, None, 2)
    invalid_handle = ctypes.c_void_p(-1).value
    if handle in (None, invalid_handle):
        error = ctypes.get_last_error()
        if error not in (50, 87):  # Unsupported flags / invalid parameter
            raise ctypes.WinError(error)
        handle = _find_first_file_ex(str(directory / "*"), 1, ctypes.byref(data), 0, None, 0)
        if handle in (None, invalid_handle):
            raise ctypes.WinError(ctypes.get_last_error())
    try:
        while True:
            name = data.cFileName
            if name not in (".", ".."):
                yield name, data.dwFileAttributes, (data.nFileSizeHigh << 32) | data.nFileSizeLow
            if not _find_next_file(handle, ctypes.byref(data)):
                error = ctypes.get_last_error()
                if error != 18:  # ERROR_NO_MORE_FILES
                    raise ctypes.WinError(error)
                break
    finally:
        _find_close(handle)


def show_windows_shell_context_menu(paths: list[Path], hwnd: int, x: int, y: int) -> bool | str:
    """Display Explorer's native IContextMenu for one or more sibling entries."""
    if os.name != "nt" or not paths:
        return False

    class GUID(ctypes.Structure):
        _fields_ = [("Data1", ctypes.c_uint32), ("Data2", ctypes.c_uint16),
                    ("Data3", ctypes.c_uint16), ("Data4", ctypes.c_ubyte * 8)]

    class CMINVOKECOMMANDINFO(ctypes.Structure):
        _fields_ = [
            ("cbSize", ctypes.c_uint32), ("fMask", ctypes.c_uint32), ("hwnd", ctypes.c_void_p),
            ("lpVerb", ctypes.c_void_p), ("lpParameters", ctypes.c_void_p),
            ("lpDirectory", ctypes.c_char_p), ("nShow", ctypes.c_int), ("dwHotKey", ctypes.c_uint32),
            ("hIcon", ctypes.c_void_p),
        ]

    def make_guid(value: str) -> GUID:
        parsed = uuid.UUID(value)
        return GUID(parsed.time_low, parsed.time_mid, parsed.time_hi_version,
                    (ctypes.c_ubyte * 8)(*parsed.bytes[8:]))

    def com_call(pointer, index: int, result_type, arg_types: tuple, *args):
        vtable = ctypes.cast(pointer, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        method = ctypes.WINFUNCTYPE(result_type, ctypes.c_void_p, *arg_types)(vtable[index])
        return method(pointer, *args)

    ole32 = ctypes.WinDLL("ole32", use_last_error=True)
    shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    comctl32 = ctypes.WinDLL("comctl32", use_last_error=True)
    co_initialize = ole32.CoInitialize
    co_initialize.argtypes = [ctypes.c_void_p]
    co_initialize.restype = ctypes.c_long
    co_uninitialize = ole32.CoUninitialize
    co_task_mem_free = ole32.CoTaskMemFree
    co_task_mem_free.argtypes = [ctypes.c_void_p]
    parse_display_name = shell32.SHParseDisplayName
    parse_display_name.argtypes = [ctypes.c_wchar_p, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p),
                                   ctypes.c_uint32, ctypes.POINTER(ctypes.c_uint32)]
    parse_display_name.restype = ctypes.c_long
    bind_to_parent = shell32.SHBindToParent
    bind_to_parent.argtypes = [ctypes.c_void_p, ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p),
                               ctypes.POINTER(ctypes.c_void_p)]
    bind_to_parent.restype = ctypes.c_long
    create_popup = user32.CreatePopupMenu
    create_popup.restype = ctypes.c_void_p
    destroy_menu = user32.DestroyMenu
    destroy_menu.argtypes = [ctypes.c_void_p]
    track_popup = user32.TrackPopupMenuEx
    track_popup.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int, ctypes.c_int,
                            ctypes.c_void_p, ctypes.c_void_p]
    track_popup.restype = ctypes.c_uint
    set_subclass = comctl32.SetWindowSubclass
    set_subclass.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t]
    set_subclass.restype = ctypes.c_int
    remove_subclass = comctl32.RemoveWindowSubclass
    remove_subclass.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t]
    remove_subclass.restype = ctypes.c_int
    default_subclass_proc = comctl32.DefSubclassProc
    default_subclass_proc.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t]
    default_subclass_proc.restype = ctypes.c_ssize_t

    init_result = co_initialize(None)
    if init_result < 0 and init_result != -2147417850:  # RPC_E_CHANGED_MODE is already initialized
        raise OSError(f"COM initialization failed: 0x{init_result & 0xFFFFFFFF:08X}")
    should_uninitialize = init_result >= 0
    pidls: list[ctypes.c_void_p] = []
    parent_folder = ctypes.c_void_p()
    context_menu = ctypes.c_void_p()
    context_menu2 = ctypes.c_void_p()
    context_menu3 = ctypes.c_void_p()
    menu = ctypes.c_void_p()
    owner_hwnd = ctypes.c_void_p(hwnd)
    subclass_id = 0x50524F53
    subclass_callback_type = ctypes.WINFUNCTYPE(
        ctypes.c_ssize_t, ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t,
        ctypes.c_ssize_t, ctypes.c_size_t, ctypes.c_size_t,
    )
    subclass_callback = None
    subclass_installed = False
    try:
        for path in paths:
            pidl = ctypes.c_void_p()
            result = parse_display_name(str(path), None, ctypes.byref(pidl), 0, None)
            if result < 0:
                raise OSError(f"Could not open Windows context menu for {path} (0x{result & 0xFFFFFFFF:08X})")
            pidls.append(pidl)

        iid_shell_folder = make_guid("000214E6-0000-0000-C000-000000000046")
        relative_first = ctypes.c_void_p()
        result = bind_to_parent(pidls[0], ctypes.byref(iid_shell_folder),
                                ctypes.byref(parent_folder), ctypes.byref(relative_first))
        if result < 0:
            raise OSError(f"Could not access the containing folder (0x{result & 0xFFFFFFFF:08X})")

        def last_item(pidl: ctypes.c_void_p) -> ctypes.c_void_p:
            offset = 0
            last_offset = 0
            while True:
                item_size = ctypes.cast(pidl.value + offset, ctypes.POINTER(ctypes.c_uint16)).contents.value
                if item_size == 0:
                    return ctypes.c_void_p(pidl.value + last_offset)
                last_offset = offset
                offset += item_size

        relative_children = [relative_first.value]
        relative_children.extend(last_item(pidl).value for pidl in pidls[1:])
        child_pidls = (ctypes.c_void_p * len(pidls))(*relative_children)
        iid_context_menu = make_guid("000214E4-0000-0000-C000-000000000046")
        result = com_call(
            parent_folder, 10, ctypes.c_long,
            (ctypes.c_void_p, ctypes.c_uint, ctypes.POINTER(ctypes.c_void_p),
             ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_uint), ctypes.POINTER(ctypes.c_void_p)),
            ctypes.c_void_p(hwnd), len(pidls), child_pidls, ctypes.byref(iid_context_menu), None,
            ctypes.byref(context_menu),
        )
        if result < 0:
            raise OSError(f"Windows could not create the context menu (0x{result & 0xFFFFFFFF:08X})")

        menu = ctypes.c_void_p(create_popup())
        if not menu:
            raise ctypes.WinError(ctypes.get_last_error())
        result = com_call(
            context_menu, 3, ctypes.c_long,
            (ctypes.c_void_p, ctypes.c_uint, ctypes.c_uint, ctypes.c_uint, ctypes.c_uint),
            menu, 0, 1, 0x7FFF, 0,
        )
        if result < 0:
            raise OSError(f"Windows could not populate the context menu (0x{result & 0xFFFFFFFF:08X})")

        iid_context_menu3 = make_guid("BCFCE0A0-EC17-11D0-8D10-00A0C90F2719")
        result = com_call(context_menu, 0, ctypes.c_long,
                          (ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p)),
                          ctypes.byref(iid_context_menu3), ctypes.byref(context_menu3))
        if result < 0:
            iid_context_menu2 = make_guid("000214F4-0000-0000-C000-000000000046")
            result = com_call(context_menu, 0, ctypes.c_long,
                              (ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p)),
                              ctypes.byref(iid_context_menu2), ctypes.byref(context_menu2))
            if result < 0:
                context_menu2 = ctypes.c_void_p()

        menu_messages = {0x0117, 0x002B, 0x002C, 0x0120}

        @subclass_callback_type
        def forward_menu_messages(window, message, wparam, lparam, current_id, reference):
            if message in menu_messages:
                if context_menu3:
                    message_result = ctypes.c_ssize_t()
                    hr = com_call(
                        context_menu3, 7, ctypes.c_long,
                        (ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t,
                         ctypes.POINTER(ctypes.c_ssize_t)),
                        message, wparam, lparam, ctypes.byref(message_result),
                    )
                    if hr >= 0:
                        return message_result.value
                elif context_menu2:
                    hr = com_call(
                        context_menu2, 6, ctypes.c_long,
                        (ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t),
                        message, wparam, lparam,
                    )
                    if hr >= 0:
                        return 0
            return default_subclass_proc(window, message, wparam, lparam)

        subclass_callback = forward_menu_messages
        subclass_installed = bool(set_subclass(owner_hwnd, subclass_callback, subclass_id, 0))
        command = track_popup(menu, 0x0102, x, y, owner_hwnd, None)
        if not command:
            return False

        command_offset = command - 1
        verb_name = ctypes.create_unicode_buffer(128)
        verb_result = com_call(
            context_menu, 5, ctypes.c_long,
            (ctypes.c_uint, ctypes.c_uint, ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_uint),
            command_offset, 4, None, verb_name, len(verb_name),
        )
        if verb_result >= 0 and verb_name.value.casefold() == "delete":
            return "delete"

        invoke = CMINVOKECOMMANDINFO()
        invoke.cbSize = ctypes.sizeof(invoke)
        invoke.fMask = 0
        invoke.hwnd = ctypes.c_void_p(hwnd)
        invoke.lpVerb = command_offset
        invoke.nShow = 1
        result = com_call(context_menu, 4, ctypes.c_long,
                          (ctypes.POINTER(CMINVOKECOMMANDINFO),), ctypes.byref(invoke))
        if result < 0:
            raise OSError(f"Windows could not run the selected command (0x{result & 0xFFFFFFFF:08X})")
        return True
    finally:
        if subclass_installed and subclass_callback:
            remove_subclass(owner_hwnd, subclass_callback, subclass_id)
        if menu:
            destroy_menu(menu)
        for pointer in (context_menu3, context_menu2, context_menu, parent_folder):
            if pointer:
                com_call(pointer, 2, ctypes.c_ulong, ())
        for pidl in pidls:
            co_task_mem_free(pidl)
        if should_uninitialize:
            co_uninitialize()


def volume_allocation_unit(root: Path) -> int:
    if _get_disk_free_space is None:
        return 4096
    sectors_per_cluster = ctypes.c_uint32()
    bytes_per_sector = ctypes.c_uint32()
    free_clusters = ctypes.c_uint32()
    total_clusters = ctypes.c_uint32()
    volume_root = root.anchor or str(root)
    if _get_disk_free_space(
        volume_root,
        ctypes.byref(sectors_per_cluster),
        ctypes.byref(bytes_per_sector),
        ctypes.byref(free_clusters),
        ctypes.byref(total_clusters),
    ):
        return max(1, sectors_per_cluster.value * bytes_per_sector.value)
    return 4096


def allocated_file_size(path: str, stat_result: os.stat_result, allocation_unit: int) -> int:
    if _get_compressed_file_size is not None:
        attributes = getattr(stat_result, "st_file_attributes", 0)
        compressed_or_sparse = bool(attributes & (0x00000800 | 0x00000200))
        if compressed_or_sparse:
            high = ctypes.c_uint32()
            ctypes.set_last_error(0)
            low = _get_compressed_file_size(path, ctypes.byref(high))
            error = ctypes.get_last_error()
            if low != 0xFFFFFFFF or error == 0:
                return (high.value << 32) | low
        size = stat_result.st_size
        return ((size + allocation_unit - 1) // allocation_unit) * allocation_unit if size else 0
    blocks = getattr(stat_result, "st_blocks", 0)
    return blocks * 512 if blocks else stat_result.st_size


@dataclass
class StorageNode:
    path: Path
    name: str
    children: list["StorageNode"] = field(default_factory=list)
    size: int = 0
    allocated: int = 0
    files: int = 0
    folders: int = 0
    extension_stats: dict[str, "ExtensionStats"] = field(default_factory=dict)
    file_entries: list["StorageFile"] = field(default_factory=list)
    files_loaded: bool = False


@dataclass
class ExtensionStats:
    size: int = 0
    allocated: int = 0
    files: int = 0


@dataclass
class StorageFile:
    path: Path
    name: str
    size: int
    allocated: int
    extension: str


class StorageScanWorker(QThread):
    progress = Signal(str, int, int)
    scan_finished = Signal(object, object, int, int)

    def __init__(self, root: Path, fast_ntfs: bool = False):
        super().__init__()
        self.root = root
        self.fast_ntfs = fast_ntfs and is_ntfs_path(root)

    def run(self) -> None:
        root_node = StorageNode(self.root, self.root.name or str(self.root))
        pending: queue.Queue[StorageNode | None] = queue.Queue()
        pending.put(root_node)
        extensions: dict[str, ExtensionStats] = defaultdict(ExtensionStats)
        allocation_unit = volume_allocation_unit(self.root)
        totals = {"directories": 0, "files": 0, "errors": 0}
        totals_lock = threading.Lock()

        def scan_directories() -> None:
            while True:
                node = pending.get()
                try:
                    if node is None:
                        return
                    local_extensions: dict[str, ExtensionStats] = defaultdict(ExtensionStats)
                    local_errors = 0
                    try:
                        if self.fast_ntfs:
                            entries = ((name, attributes, size, node.path / name)
                                       for name, attributes, size in fast_windows_entries(node.path))
                            for name, attributes, size, entry_path in entries:
                                try:
                                    is_directory = bool(attributes & 0x10)
                                    is_reparse = bool(attributes & 0x400)
                                    if is_directory and not is_reparse:
                                        node.children.append(StorageNode(entry_path, name))
                                    elif not is_directory and not is_reparse:
                                        # Ordinary NTFS files can be estimated by cluster rounding.
                                        # Compressed and sparse files need their physical on-disk
                                        # allocation, otherwise logical size is over-counted.
                                        if attributes & (0x00000800 | 0x00000200):
                                            file_stat = os.stat(entry_path, follow_symlinks=False)
                                            allocated = allocated_file_size(str(entry_path), file_stat, allocation_unit)
                                        else:
                                            allocated = ((size + allocation_unit - 1) // allocation_unit) * allocation_unit if size else 0
                                        extension = os.path.splitext(name)[1].casefold() or "(No Extension)"
                                        stats = local_extensions[extension]
                                        node.size += size
                                        node.allocated += allocated
                                        node.files += 1
                                        stats.size += size
                                        stats.allocated += allocated
                                        stats.files += 1
                                except OSError:
                                    local_errors += 1
                        else:
                            with os.scandir(node.path) as entries:
                                for entry in entries:
                                    try:
                                        if entry.is_dir(follow_symlinks=False):
                                            node.children.append(StorageNode(Path(entry.path), entry.name))
                                        elif entry.is_file(follow_symlinks=False):
                                            stat = entry.stat(follow_symlinks=False)
                                            size = stat.st_size
                                            allocated = allocated_file_size(entry.path, stat, allocation_unit)
                                            extension = os.path.splitext(entry.name)[1].casefold() or "(No Extension)"
                                            stats = local_extensions[extension]
                                            node.size += size
                                            node.allocated += allocated
                                            node.files += 1
                                            stats.size += size
                                            stats.allocated += allocated
                                            stats.files += 1
                                    except OSError:
                                        local_errors += 1
                    except OSError:
                        local_errors += 1

                    for child in node.children:
                        pending.put(child)

                    with totals_lock:
                        node.extension_stats = dict(local_extensions)
                        totals["directories"] += 1
                        totals["files"] += node.files
                        totals["errors"] += local_errors
                        for extension, local in local_extensions.items():
                            aggregate = extensions[extension]
                            aggregate.size += local.size
                            aggregate.allocated += local.allocated
                            aggregate.files += local.files
                        if totals["directories"] % 250 == 0:
                            self.progress.emit(
                                str(node.path), totals["directories"], totals["files"]
                            )
                finally:
                    pending.task_done()

        worker_count = min(8, max(2, os.cpu_count() or 4))
        with ThreadPoolExecutor(max_workers=worker_count, thread_name_prefix="storage-scan") as pool:
            workers = [pool.submit(scan_directories) for _ in range(worker_count)]
            pending.join()
            for _ in workers:
                pending.put(None)
            for worker in workers:
                worker.result()

        nodes = []
        to_visit = [root_node]
        while to_visit:
            node = to_visit.pop()
            nodes.append(node)
            to_visit.extend(node.children)

        for node in reversed(nodes):
            node.children.sort(key=lambda child: child.allocated, reverse=True)
            for child in node.children:
                node.size += child.size
                node.allocated += child.allocated
                node.files += child.files
                node.folders += child.folders + 1
                for extension, stats in child.extension_stats.items():
                    aggregate = node.extension_stats.setdefault(extension, ExtensionStats())
                    aggregate.size += stats.size
                    aggregate.allocated += stats.allocated
                    aggregate.files += stats.files

        self.scan_finished.emit(
            root_node, dict(extensions), totals["errors"], totals["directories"]
        )


def send_to_recycle_bin(path: Path) -> None:
    """Send a file or folder to the Windows Recycle Bin."""
    class SHFILEOPSTRUCTW(ctypes.Structure):
        _fields_ = [
            ("hwnd", ctypes.c_void_p), ("wFunc", ctypes.c_uint),
            ("pFrom", ctypes.c_wchar_p), ("pTo", ctypes.c_wchar_p),
            ("fFlags", ctypes.c_ushort), ("fAnyOperationsAborted", ctypes.c_bool),
            ("hNameMappings", ctypes.c_void_p), ("lpszProgressTitle", ctypes.c_wchar_p),
        ]

    operation = SHFILEOPSTRUCTW()
    operation.wFunc = 3
    operation.pFrom = str(path) + "\0"
    operation.fFlags = 0x0040 | 0x0010 | 0x0004 | 0x0400
    result = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(operation))
    if result != 0 or operation.fAnyOperationsAborted:
        raise OSError(result or "Delete operation was cancelled")


def make_table(headers: list[str], parent: QWidget) -> TableWidget:
    table = TableWidget(parent)
    table.setColumnCount(len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.setBorderVisible(True)
    table.setBorderRadius(8)
    table.setAlternatingRowColors(True)
    table.setEditTriggers(TableWidget.EditTrigger.NoEditTriggers)
    table.setSelectionBehavior(TableWidget.SelectionBehavior.SelectRows)
    table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    table.verticalHeader().hide()
    return table


def set_item(table: TableWidget, row: int, column: int, value: str) -> None:
    table.setItem(row, column, QTableWidgetItem(value))


def show_info(parent: QWidget, title: str, text: str) -> None:
    QMessageBox.information(parent, title, text)


def show_error(parent: QWidget, title: str, text: str) -> None:
    QMessageBox.critical(parent, title, text)


def confirm(parent: QWidget, title: str, text: str) -> bool:
    return QMessageBox.question(parent, title, text, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes


class NoScrollbarComboBox(ComboBox):
    """Fluent dropdown with a clean popup and no visible scrollbars."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setObjectName("stableComboBox")
        self._locked_height = 32
        self._lock_layout_size = True
        self.setFixedHeight(32)
        self.currentIndexChanged.connect(self._queue_height_lock)

    def lock_height(self, height: int) -> None:
        self._locked_height = height
        self._lock_layout_size = True
        self.setFixedHeight(height)

    def adjustSize(self) -> None:
        # QFluent's ComboBox calls adjustSize() whenever its selected text
        # changes; layout-managed rule fields must retain their assigned size.
        if getattr(self, "_lock_layout_size", False):
            return
        super().adjustSize()

    def _onItemClicked(self, index: int) -> None:
        super()._onItemClicked(index)
        if self._lock_layout_size:
            self.setFixedHeight(self._locked_height)

    def _queue_height_lock(self, *_args) -> None:
        if not self._lock_layout_size:
            return
        self.setFixedHeight(self._locked_height)
        # QFluent can update its button text and layout after emitting the
        # selection signal, so reapply the locked height on the next event turn.
        QTimer.singleShot(0, self._apply_height_lock)

    def _apply_height_lock(self) -> None:
        if self._lock_layout_size:
            self.setFixedHeight(self._locked_height)

    def _showComboMenu(self):
        if not self.items:
            return

        menu = self._createComboMenu()
        for index, item in enumerate(self.items):
            action = QAction(item.icon, item.text, menu)
            action.setEnabled(item.isEnabled)
            action.triggered.connect(
                lambda _checked=False, item_index=index: self._onItemClicked(item_index)
            )
            menu.addAction(action)

        # Keep Fluent's default compact menu item sizing.
        menu.setItemHeight(24)
        menu.setMaxVisibleItems(len(self.items))
        menu.setMinimumWidth(self.width())
        menu.view.setObjectName("comboPopupList")
        menu.view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        menu.view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        menu.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        menu.closedSignal.connect(self._onDropMenuClosed)
        self.dropMenu = menu

        if self.currentIndex() >= 0:
            menu.setDefaultAction(menu.actions()[self.currentIndex()])

        selector_top = self.mapToGlobal(QPoint(0, 0))
        selector_bottom = self.mapToGlobal(QPoint(0, self.height()))
        popup_x = selector_top.x()
        screen = self.screen()
        if screen is not None:
            available = screen.availableGeometry()
            popup_x = max(available.left(), min(popup_x, available.right() - menu.width() + 1))
        below = QPoint(popup_x, selector_bottom.y())
        above = QPoint(popup_x, selector_top.y())
        drop_height = menu.view.heightForAnimation(below, MenuAnimationType.DROP_DOWN)
        pull_height = menu.view.heightForAnimation(above, MenuAnimationType.PULL_UP)
        if drop_height >= pull_height:
            menu.view.adjustSize(below, MenuAnimationType.DROP_DOWN)
            menu.exec(below, aniType=MenuAnimationType.DROP_DOWN)
        else:
            menu.view.adjustSize(above, MenuAnimationType.PULL_UP)
            menu.exec(above, aniType=MenuAnimationType.PULL_UP)

    def _createComboMenu(self):
        menu = super()._createComboMenu()
        menu.view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        menu.view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        return menu


class VerticallyShiftedFluentIcon(FluentIconBase):
    """Keep tab icons optically centered against their labels."""

    def __init__(self, source: FluentIconBase, offset_y: float = -2):
        self.source = source
        self.offset_y = offset_y

    def path(self, theme=Theme.AUTO):
        return self.source.path(theme)

    def icon(self, theme=Theme.AUTO, color=None):
        return self.source.icon(theme, color)

    def render(self, painter, rect, theme=Theme.AUTO, indexes=None, **attributes):
        self.source.render(
            painter, QRectF(rect).translated(0, self.offset_y),
            theme=theme, indexes=indexes, **attributes
        )


class ConditionDeleteToolButton(ToolButton):
    """Compact, fixed-geometry remove button for every rule condition row."""

    def __init__(self, icon: FluentIconBase, parent: QWidget | None = None):
        super().__init__(parent)
        self.setIcon(icon)
        self.setObjectName("conditionRemoveButton")
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.setIconSize(QSize(16, 16))
        # ToolButton's bundled stylesheet includes generous padding. Override
        # it locally so dynamically added rows keep the same compact geometry
        # as the first row even after Qt repolishes the widget.
        self.setStyleSheet(
            self.styleSheet()
            + "\nQToolButton#conditionRemoveButton { min-width:28px; max-width:28px; "
            "min-height:28px; max-height:28px; padding:0px; }"
        )
        self.setFixedSize(30, 30)

    def sizeHint(self) -> QSize:
        return QSize(30, 30)

    def minimumSizeHint(self) -> QSize:
        return QSize(30, 30)


def align_tab_icon(item, offset_y: float = -2) -> None:
    if hasattr(item, "_prosoft_unshifted_icon"):
        return
    icon = getattr(item, "_icon", None)
    if isinstance(icon, FluentIconBase):
        item._prosoft_unshifted_icon = icon
        item.setIcon(VerticallyShiftedFluentIcon(icon, offset_y))


class ConditionRow(QWidget):
    def __init__(self, on_remove, parent: QWidget | None = None, fields: tuple[str, ...] | None = None):
        super().__init__(parent)
        self.setFixedHeight(36)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(6)
        self.connector_widget = QWidget(self)
        connector_layout = QHBoxLayout(self.connector_widget)
        connector_layout.setContentsMargins(0, 0, 0, 0)
        connector_layout.setSpacing(0)
        self.logic_operator = NoScrollbarComboBox(self.connector_widget)
        self.logic_operator.addItems(["AND", "OR", "NOT"])
        self.logic_operator.setCurrentText("AND")
        self.logic_operator.setFixedWidth(72)
        self.logic_label = BodyLabel("IF", self.connector_widget)
        self.logic_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.logic_label.setFixedSize(72, 32)
        connector_layout.addWidget(self.logic_operator)
        connector_layout.addWidget(self.logic_label)
        layout.addWidget(self.connector_widget)
        self.field = NoScrollbarComboBox(self)
        self.available_fields = fields or ("File Type", "File Extension", "File Size", "File Name", "File Date")
        self.field.addItems(list(self.available_fields))
        self.field.setCurrentText("File Extension" if "File Extension" in self.available_fields else self.available_fields[0])
        self.operator = NoScrollbarComboBox(self)
        self.operator.addItems(TYPE_OPERATORS)
        self.value = LineEdit(self)
        self.value.setPlaceholderText("e.g. .jpg, Video, 10")
        self.type_value = NoScrollbarComboBox(self)
        self.type_value.addItems(list(CATEGORIES) + ["Other"])
        self.type_value.setPlaceholderText("Select file type")
        self.type_value.setCurrentIndex(-1)
        self.unit = NoScrollbarComboBox(self)
        self.unit.addItems(list(SIZE_UNITS))
        self.unit.setCurrentText("MB")
        self.name_date = NoScrollbarComboBox(self)
        self.name_date.addItems(["Date created", "Date modified", "Date last accessed"])
        self.date_start = QDateEdit(self)
        self.date_start.setCalendarPopup(True)
        self.date_start.setDisplayFormat("MM-dd-yyyy")
        self.date_start.setDate(QDate.currentDate())
        self.date_end = QDateEdit(self)
        self.date_end.setCalendarPopup(True)
        self.date_end.setDisplayFormat("MM-dd-yyyy")
        self.date_end.setDate(QDate.currentDate())
        self.date_period = QSpinBox(self)
        self.date_period.setRange(1, 9999)
        self.date_period.setValue(7)
        self.date_period_unit = NoScrollbarComboBox(self)
        self.date_period_unit.addItems(["Days", "Months", "Years"])
        self.date_period_unit.setCurrentText("Days")
        self.remove_button = ConditionDeleteToolButton(FluentIcon.DELETE, self)
        self.remove_button.setToolTip("Remove condition")
        self.remove_button.setAccessibleName("Remove condition")
        self.remove_button.clicked.connect(on_remove)
        layout.addWidget(self.field, 2)
        layout.addWidget(self.operator, 2)
        layout.addWidget(self.value, 3)
        layout.addWidget(self.type_value, 3)
        self.type_value.hide()
        layout.addWidget(self.unit)
        layout.addWidget(self.name_date, 2)
        layout.addWidget(self.date_start, 2)
        layout.addWidget(self.date_end, 2)
        layout.addWidget(self.date_period, 1)
        layout.addWidget(self.date_period_unit, 1)
        layout.addWidget(self.remove_button)
        for combo in (
            self.field, self.operator, self.type_value,
            self.name_date, self.date_period_unit,
        ):
            combo.setMinimumWidth(0)
            combo.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
            combo.lock_height(32)
        self.logic_operator.setFixedWidth(72)
        self.logic_operator.lock_height(32)
        self.unit.setFixedWidth(72)
        self.unit.lock_height(30)
        self.logic_label.setFixedHeight(32)
        self.logic_operator.hide()
        for control in (
            self.value, self.date_start, self.date_end,
            self.date_period,
        ):
            control.setFixedHeight(30)
        self.field.currentTextChanged.connect(self.update_field)
        self.operator.currentTextChanged.connect(self.update_operator)
        self.update_field(self.field.currentText())

    def update_field(self, field: str) -> None:
        self.operator.clear()
        operators = {
            "File Size": SIZE_OPERATORS,
            "File Name": NAME_OPERATORS,
            "File Date": DATE_OPERATORS,
        }.get(field, TYPE_OPERATORS)
        self.operator.addItems(operators)
        self.value.clear()
        self.value.setVisible(field in ("File Extension", "File Size", "File Name"))
        self.type_value.setVisible(field == "File Type")
        self.unit.setVisible(field == "File Size")
        self.name_date.setVisible(field == "File Date")
        self.update_operator(self.operator.currentText())
        if field == "File Type":
            self.type_value.setCurrentIndex(-1)
        elif field == "File Extension":
            self.value.setPlaceholderText("e.g. .jpg or .tar.gz")
        elif field == "File Size":
            self.value.setPlaceholderText("Enter a size")
        elif field == "File Name":
            self.value.setPlaceholderText("Enter a file name or pattern")

    def update_operator(self, operator: str) -> None:
        is_date = self.field.currentText() == "File Date"
        self.date_start.setVisible(is_date and operator in ("Before", "After", "Between"))
        self.date_end.setVisible(is_date and operator == "Between")
        relative = is_date and operator in ("Within last", "Older than", "Newer than")
        self.date_period.setVisible(relative)
        self.date_period_unit.setVisible(relative)


