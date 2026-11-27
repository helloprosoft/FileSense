"""Windows startup discovery and guarded controls for FileSense."""

from __future__ import annotations

import base64
import ctypes
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, QSettings, QThread, QTimer, Signal
from PySide6.QtGui import QFont
if os.environ.get("FILESENSE_QML_RUNTIME") == "1":
    class _WidgetsUiOnly:
        pass

    (QAbstractItemView, QHeaderView, QHBoxLayout, QLabel, QMessageBox, QProgressBar,
     QTabWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget, BodyLabel,
     CaptionLabel, CardWidget, FluentIcon, PrimaryPushButton, PushButton,
     StrongBodyLabel, SubtitleLabel, TitleLabel) = (_WidgetsUiOnly,) * 20
else:
    from PySide6.QtWidgets import (
        QAbstractItemView, QHeaderView, QHBoxLayout, QLabel, QMessageBox, QProgressBar,
        QTabWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
    )
    from qfluentwidgets import (
        BodyLabel, CaptionLabel, CardWidget, FluentIcon, PrimaryPushButton,
        PushButton, StrongBodyLabel, SubtitleLabel, TitleLabel,
    )


REGISTRY_LOCATIONS = (
    ("HKCU", r"Software\Microsoft\Windows\CurrentVersion\Run", "Current-user Run", "Startup apps"),
    ("HKLM", r"Software\Microsoft\Windows\CurrentVersion\Run", "All-users Run", "Startup apps"),
    ("HKCU", r"Software\Microsoft\Windows\CurrentVersion\RunOnce", "Current-user RunOnce", "Startup apps"),
    ("HKLM", r"Software\Microsoft\Windows\CurrentVersion\RunOnce", "All-users RunOnce", "Startup apps"),
)
POLICY_LOCATIONS = (
    ("HKCU", r"Software\Microsoft\Windows\CurrentVersion\Policies\Explorer\Run"),
    ("HKLM", r"Software\Microsoft\Windows\CurrentVersion\Policies\Explorer\Run"),
    ("HKCU", r"Software\Policies\Microsoft\Windows\System\Scripts\Logon"),
    ("HKLM", r"Software\Policies\Microsoft\Windows\System\Scripts\Logon"),
)
STARTUP_APPROVED_LOCATIONS = (
    ("HKCU", r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run"),
    ("HKCU", r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run32"),
    ("HKCU", r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\StartupFolder"),
    ("HKLM", r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run"),
    ("HKLM", r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run32"),
    ("HKLM", r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\StartupFolder"),
)
TAB_CATEGORIES = ("Startup apps", "Scheduled tasks", "Services", "Startup Approved", "Policies")
SERVICE_PROTECTION_NAMES = {
    "bfe", "cryptsvc", "dcomlaunch", "eventlog", "gpsvc", "lsm", "mpssvc",
    "plugplay", "power", "profsvc", "rpcss", "samss", "schedule", "sense",
    "trustedinstaller", "windefend", "wscsvc", "wdnissvc", "securityhealthservice",
}


class StartupConfirmationRequired(RuntimeError):
    def __init__(self, title: str, message: str):
        super().__init__(message)
        self.title = title
        self.message = message


@dataclass
class AutorunEntry:
    entry_id: str
    name: str
    category: str
    source: str
    location: str
    command: str = ""
    executable: str = ""
    arguments: str = ""
    publisher: str = "Unknown"
    signature: str = "Unknown"
    file_exists: str = "Unknown"
    status: str = "Unknown"
    safety: str = "Unknown"
    impact: str = "Unknown"
    duplicate: bool = False
    controllable: bool = False
    protected: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


def _powershell(script: str, stdin: str = "", timeout: int = 45) -> subprocess.CompletedProcess[str]:
    encoded = base64.b64encode(script.encode("utf-16le")).decode("ascii")
    return subprocess.run(
        ["powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
        input=stdin, capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=timeout, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), check=False,
    )


def _command_parts(command: str) -> tuple[str, str]:
    """Split a Windows command line using the native Windows parser."""
    if not command.strip():
        return "", ""
    # A scheduled task may store an executable path with spaces without quoting
    # it and place the remaining path segments in Arguments. Prefer the longest
    # path ending at a known executable extension before invoking argv parsing.
    unquoted_path = re.match(
        r"^\s*((?:[A-Za-z]:\\|\\\\).*?\.(?:exe|com|bat|cmd|ps1|vbs|js|dll))(?=\s|$)\s*(.*)$",
        command, re.IGNORECASE,
    )
    if unquoted_path:
        return unquoted_path.group(1), unquoted_path.group(2)
    if os.name == "nt":
        shell32 = ctypes.WinDLL("shell32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        shell32.CommandLineToArgvW.argtypes = [ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_int)]
        shell32.CommandLineToArgvW.restype = ctypes.POINTER(ctypes.c_wchar_p)
        count = ctypes.c_int()
        argv = shell32.CommandLineToArgvW(command, ctypes.byref(count))
        if argv:
            try:
                values = [argv[index] for index in range(count.value)]
            finally:
                kernel32.LocalFree.argtypes = [ctypes.c_void_p]
                kernel32.LocalFree(argv)
            return (values[0], subprocess.list2cmdline(values[1:])) if values else ("", "")
    match = re.match(r'^\s*"([^"]+)"\s*(.*)$', command)
    if match:
        return match.group(1), match.group(2)
    match = re.match(r"^\s*(.+?\.(?:exe|com|bat|cmd|ps1|vbs|js|dll))(?:\s+(.*))?$", command, re.I)
    return (match.group(1), match.group(2) or "") if match else (command.strip().split(" ", 1)[0], "")


def _resolve_reference(command: str) -> tuple[str, str]:
    executable, arguments = _command_parts(os.path.expandvars(command))
    if not executable:
        return "", ""
    name = Path(executable.strip('"')).name.casefold()
    args, reference = arguments, executable
    try:
        tokens = ctypes_args(arguments) if os.name == "nt" else arguments.split()
    except Exception:
        tokens = arguments.split()
    if name in ("rundll32.exe", "regsvr32.exe", "regsvr32") and tokens:
        reference = tokens[0].split(",", 1)[0].strip('"')
    elif name in ("wscript.exe", "cscript.exe", "mshta.exe") and tokens:
        reference = tokens[0].strip('"')
    elif name == "cmd.exe" and len(tokens) >= 2 and tokens[0].casefold() in ("/c", "/k"):
        reference = tokens[1].strip('"')
    elif name in ("powershell.exe", "pwsh.exe"):
        for index, token in enumerate(tokens[:-1]):
            if token.casefold() in ("-file", "-f"):
                reference = tokens[index + 1].strip('"')
                break
    reference = os.path.expandvars(reference)
    if reference.casefold().startswith("\\systemroot\\"):
        reference = str(Path(os.environ.get("SystemRoot", r"C:\Windows")) / reference[len("\\SystemRoot\\"):])
    elif reference.startswith("\\??\\"):
        reference = reference[4:]
    candidate = Path(reference.strip('"'))
    if not candidate.is_absolute():
        located = shutil.which(reference.strip('"'))
        if located:
            reference = located
    return reference, arguments


def ctypes_args(arguments: str) -> list[str]:
    if not arguments.strip():
        return []
    shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    shell32.CommandLineToArgvW.argtypes = [ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_int)]
    shell32.CommandLineToArgvW.restype = ctypes.POINTER(ctypes.c_wchar_p)
    count = ctypes.c_int()
    argv = shell32.CommandLineToArgvW(arguments, ctypes.byref(count))
    if not argv:
        return []
    try:
        return [argv[index] for index in range(count.value)]
    finally:
        kernel32.LocalFree.argtypes = [ctypes.c_void_p]
        kernel32.LocalFree(argv)


def _reg_data_to_json(value: Any) -> dict[str, Any]:
    if isinstance(value, bytes):
        return {"kind": "bytes", "value": base64.b64encode(value).decode("ascii")}
    return {"kind": "plain", "value": value}


def _reg_data_from_json(data: dict[str, Any]) -> Any:
    if data.get("kind") == "bytes":
        return base64.b64decode(data.get("value", ""))
    return data.get("value")


def _startup_approved_status(data: Any) -> str:
    if not isinstance(data, bytes) or not data:
        return "Unknown"
    state = data[0]
    if state in (0x02, 0x04, 0x06):
        return "Enabled"
    if state in (0x03, 0x05, 0x07):
        return "Disabled"
    return "Unknown"


class AutorunScanner:
    def __init__(self, settings: QSettings):
        self.settings = settings
        self.errors: list[str] = []

    def scan(self) -> tuple[list[AutorunEntry], str, str, list[str]]:
        if os.name != "nt":
            raise OSError("Startup Manager is available only on Windows.")
        import winreg

        entries: list[AutorunEntry] = []
        approved = self._read_approved(winreg)
        entries.extend(self._read_registry_autoruns(winreg, approved))
        entries.extend(self._read_startup_folders(approved))
        entries.extend(self._read_tasks())
        entries.extend(self._read_services())
        entries.extend(self._read_approved_records(winreg))
        self._apply_approval_states(entries)
        entries.extend(self._read_policies(winreg))
        live_ids = {entry.entry_id.casefold() for entry in entries}
        entries.extend(entry for entry in self._restore_disabled_records() if entry.entry_id.casefold() not in live_ids)
        self._read_signatures(entries)
        self._assess_entries(entries)
        windows_version = platform.version()
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion") as key:
                product = winreg.QueryValueEx(key, "ProductName")[0]
                display_version = winreg.QueryValueEx(key, "DisplayVersion")[0] if self._has_value(winreg, key, "DisplayVersion") else ""
                windows_version = f"{product} {display_version} ({platform.version()})".strip()
        except OSError:
            pass
        architecture = f"{platform.machine()} / {platform.architecture()[0]}"
        return self._deduplicate(entries), windows_version, architecture, self.errors

    @staticmethod
    def _apply_approval_states(entries: list[AutorunEntry]) -> None:
        approval_records = [entry for entry in entries if entry.category == "Startup Approved"]
        for entry in entries:
            if entry.category != "Startup apps":
                continue
            metadata = entry.metadata
            if metadata.get("kind") == "registry":
                approval_key = str(metadata.get("key", "")).rsplit("\\", 1)[-1].casefold()
                approval_name = entry.name.casefold()
                approval_hive = str(metadata.get("hive", "")).casefold()
                if approval_key != "run":
                    continue
                approval_key = "run32" if "32-bit view" in entry.entry_id else "run"
            elif metadata.get("kind") == "startup_folder":
                approval_key = "startupfolder"
                approval_name = Path(metadata.get("original_path", entry.name)).name.casefold()
                approval_hive = "hklm" if entry.source.startswith("All-users") else "hkcu"
            else:
                continue
            matches = [
                approved for approved in approval_records
                if str(approved.metadata.get("hive", "")).casefold() == approval_hive
                and str(approved.metadata.get("key", "")).rsplit("\\", 1)[-1].casefold() == approval_key
                and approved.name.casefold() == approval_name
            ]
            if matches and matches[0].status in ("Enabled", "Disabled"):
                approval = matches[0]
                entry.status = approval.status
                entry.metadata["approval_entry_id"] = approval.entry_id
                entry.metadata["approval_status"] = approval.status

    @staticmethod
    def _has_value(winreg, key, name: str) -> bool:
        try:
            winreg.QueryValueEx(key, name)
            return True
        except OSError:
            return False

    def _read_approved(self, winreg) -> dict[tuple[str, str], str]:
        result: dict[tuple[str, str], str] = {}
        hives = {"HKCU": winreg.HKEY_CURRENT_USER, "HKLM": winreg.HKEY_LOCAL_MACHINE}
        for hive_name, key_path in STARTUP_APPROVED_LOCATIONS:
            for view, suffix in ((winreg.KEY_WOW64_64KEY, "64-bit"), (winreg.KEY_WOW64_32KEY, "32-bit")):
                try:
                    with winreg.OpenKey(hives[hive_name], key_path, 0, winreg.KEY_READ | view) as key:
                        for index in range(winreg.QueryInfoKey(key)[1]):
                            name, data, _kind = winreg.EnumValue(key, index)
                            if isinstance(data, bytes) and data:
                                state = _startup_approved_status(data)
                                result[(key_path.rsplit("\\", 1)[-1].casefold(), name.casefold())] = state
                                result[(key_path.rsplit("\\", 1)[-1].casefold(), f"{hive_name}:{name}".casefold())] = state
                except OSError as error:
                    if getattr(error, "winerror", None) not in (2, 3):
                        self.errors.append(f"Could not read {hive_name}\\{key_path}: {error}")
        return result

    def _registry_value_entries(self, hive_name: str, key_path: str, source: str,
                                category: str, winreg) -> list[AutorunEntry]:
        hives = {"HKCU": winreg.HKEY_CURRENT_USER, "HKLM": winreg.HKEY_LOCAL_MACHINE}
        entries = []
        seen: set[tuple[str, str]] = set()
        for view, view_label in ((winreg.KEY_WOW64_64KEY, "64-bit view"), (winreg.KEY_WOW64_32KEY, "32-bit view")):
            try:
                with winreg.OpenKey(hives[hive_name], key_path, 0, winreg.KEY_READ | view) as key:
                    for index in range(winreg.QueryInfoKey(key)[1]):
                        name, value, value_type = winreg.EnumValue(key, index)
                        unique = (name.casefold(), str(value).casefold())
                        if unique in seen:
                            continue
                        seen.add(unique)
                        command = str(value)
                        executable, arguments = _resolve_reference(command)
                        entry_id = f"registry:{hive_name}:{view_label}:{key_path}:{name}"
                        entries.append(AutorunEntry(
                            entry_id=entry_id, name=name, category=category,
                            source=source, location=f"{hive_name}\\{key_path} ({view_label})",
                            command=command, executable=executable, arguments=arguments,
                            status="Enabled", controllable=True,
                            metadata={"kind": "registry", "hive": hive_name, "key": key_path,
                                      "view": view, "value_name": name, "value_type": value_type,
                                      "value_data": _reg_data_to_json(value)},
                        ))
            except OSError as error:
                if getattr(error, "winerror", None) not in (2, 3):
                    self.errors.append(f"Could not read {hive_name}\\{key_path}: {error}")
        return entries

    def _read_registry_autoruns(self, winreg, approved: dict[tuple[str, str], str]) -> list[AutorunEntry]:
        entries = []
        for hive, key, source, category in REGISTRY_LOCATIONS:
            for entry in self._registry_value_entries(hive, key, source, category, winreg):
                approval_key = ("runonce" if "RunOnce" in key else "run", entry.name.casefold())
                entry.status = "Enabled"
                entry.metadata["approval_status"] = approved.get(approval_key, "Unknown")
                entries.append(entry)
        return entries

    def _startup_paths(self) -> list[tuple[Path, str]]:
        appdata = Path(os.environ.get("APPDATA", Path.home() / "AppData/Roaming"))
        programdata = Path(os.environ.get("PROGRAMDATA", "C:/ProgramData"))
        return [
            (appdata / "Microsoft/Windows/Start Menu/Programs/Startup", "Current-user Startup folder"),
            (programdata / "Microsoft/Windows/Start Menu/Programs/Startup", "All-users Startup folder"),
        ]

    @staticmethod
    def _resolve_shortcut(path: Path) -> str:
        escaped = str(path).replace("'", "''")
        script = (
            "$s=(New-Object -ComObject WScript.Shell).CreateShortcut('" + escaped + "'); "
            "[pscustomobject]@{Target=$s.TargetPath;Arguments=$s.Arguments;WorkingDirectory=$s.WorkingDirectory} "
            "| ConvertTo-Json -Compress"
        )
        try:
            result = _powershell(script, timeout=10)
            if result.returncode == 0 and result.stdout.strip():
                data = json.loads(result.stdout)
                return " ".join(part for part in (data.get("Target", ""), data.get("Arguments", "")) if part)
        except (OSError, subprocess.SubprocessError, ValueError, json.JSONDecodeError):
            pass
        return ""

    def _read_startup_folders(self, approved: dict[tuple[str, str], str]) -> list[AutorunEntry]:
        entries = []
        for folder, source in self._startup_paths():
            if not folder.is_dir():
                continue
            try:
                children = sorted(folder.iterdir(), key=lambda item: item.name.casefold())
            except OSError as error:
                self.errors.append(f"Could not list startup folder {folder}: {error}")
                continue
            for child in children:
                if not child.is_file():
                    continue
                command = self._resolve_shortcut(child) if child.suffix.casefold() == ".lnk" else str(child)
                executable, arguments = _resolve_reference(command or str(child))
                approval_status = approved.get(("startupfolder", child.name.casefold()), "Unknown")
                entries.append(AutorunEntry(
                    entry_id=f"startup-folder:{child.resolve()}", name=child.stem,
                    category="Startup apps", source=source, location=str(child),
                    command=command or str(child), executable=executable, arguments=arguments,
                    status="Enabled", controllable=True,
                    metadata={"kind": "startup_folder", "original_path": str(child),
                              "approval_status": approval_status},
                ))
        return entries

    @staticmethod
    def _json_command(script: str, timeout: int = 60) -> list[dict[str, Any]]:
        result = _powershell(script, timeout=timeout)
        if result.returncode != 0:
            raise OSError(result.stderr.strip() or "PowerShell query failed")
        output = result.stdout.strip()
        if not output:
            return []
        parsed = json.loads(output)
        if isinstance(parsed, dict):
            return [parsed]
        records: list[dict[str, Any]] = []
        pending = list(parsed) if isinstance(parsed, list) else []
        while pending:
            item = pending.pop(0)
            if isinstance(item, dict):
                records.append(item)
            elif isinstance(item, list):
                pending[0:0] = item
        return records

    def _read_tasks(self) -> list[AutorunEntry]:
        script = r"""
$ErrorActionPreference='Stop'
$scheduler = New-Object -ComObject Schedule.Service
$scheduler.Connect()
function Read-TaskFolder($folder) {
  $rows = @()
  foreach ($task in $folder.GetTasks(1)) {
    $startup = @()
    foreach ($trigger in $task.Definition.Triggers) {
      if ([int]$trigger.Type -eq 8) { $startup += 'Boot' }
      elseif ([int]$trigger.Type -eq 9) { $startup += 'Logon' }
    }
    if ($startup.Count -gt 0) {
      $actions = @()
      foreach ($action in $task.Definition.Actions) {
        if ([int]$action.Type -eq 0) {
          $actions += [pscustomobject]@{Execute=[string]$action.Path;Arguments=[string]$action.Arguments;WorkingDirectory=[string]$action.WorkingDirectory}
        } else {
          $actions += [pscustomobject]@{Execute='';Arguments='';WorkingDirectory=''}
        }
      }
      $rows += [pscustomobject]@{Name=$task.Name;Path=$folder.Path;Enabled=[bool]$task.Enabled;Triggers=$startup;Actions=$actions;Author=[string]$task.Definition.RegistrationInfo.Author}
    }
  }
  foreach ($child in $folder.GetFolders(0)) { $rows += Read-TaskFolder $child }
  return ,$rows
}
$items = @(Read-TaskFolder ($scheduler.GetFolder('\')))
ConvertTo-Json -InputObject $items -Depth 5 -Compress
"""
        try:
            records = self._json_command(script)
        except (OSError, subprocess.SubprocessError, ValueError, json.JSONDecodeError) as error:
            records = self._read_tasks_from_files()
            if not records:
                self.errors.append(f"Could not enumerate Scheduled Tasks: {error}")
                return []
        entries = []
        for task in records:
            actions = task.get("Actions") or []
            if isinstance(actions, dict):
                actions = [actions]
            commands = []
            for action in actions:
                command = " ".join(part for part in (str(action.get("Execute") or ""), str(action.get("Arguments") or "")) if part)
                if command:
                    commands.append(command)
            task_folder = str(task.get("Path") or "\\").rstrip("\\")
            task_name = str(task.get("Name") or "")
            task_path = f"{task_folder}\\{task_name}" if task_folder else f"\\{task_name}"
            command = " | ".join(commands)
            executable, arguments = _resolve_reference(command)
            enabled = bool(task.get("Enabled"))
            entries.append(AutorunEntry(
                entry_id=f"task:{task_path}", name=str(task.get("Name") or task_path),
                category="Scheduled tasks", source="Scheduled Task (startup/logon trigger)",
                location=task_path, command=command, executable=executable, arguments=arguments,
                status="Enabled" if enabled else "Disabled", controllable=True,
                metadata={"kind": "task", "task_path": task_path, "triggers": task.get("Triggers", []),
                          "author": task.get("Author", "")},
            ))
        return entries

    def _read_tasks_from_files(self) -> list[dict[str, Any]]:
        """Read task XML files when Task Scheduler's query interface is unavailable."""
        root = Path(os.environ.get("WINDIR", "C:/Windows")) / "System32/Tasks"
        if not root.is_dir():
            return []
        records: list[dict[str, Any]] = []
        def local_name(tag: str) -> str:
            return tag.rsplit("}", 1)[-1]
        try:
            for directory, _subdirs, filenames in os.walk(root):
                for filename in filenames:
                    path = Path(directory) / filename
                    try:
                        if path.stat().st_size > 2_000_000:
                            continue
                        document = ET.parse(path).getroot()
                    except (OSError, ET.ParseError):
                        continue
                    trigger_types = [
                        local_name(node.tag)[:-7]
                        for node in document.iter()
                        if local_name(node.tag) in ("BootTrigger", "LogonTrigger")
                    ]
                    if not trigger_types:
                        continue
                    actions = []
                    for action in document.iter():
                        if local_name(action.tag) != "Exec":
                            continue
                        values = {local_name(child.tag): (child.text or "") for child in action}
                        actions.append({
                            "Execute": values.get("Command", ""),
                            "Arguments": values.get("Arguments", ""),
                            "WorkingDirectory": values.get("WorkingDirectory", ""),
                        })
                    settings = next((node for node in document.iter() if local_name(node.tag) == "Settings"), None)
                    enabled_node = next((node for node in settings or () if local_name(node.tag) == "Enabled"), None)
                    author_node = next((node for node in document.iter() if local_name(node.tag) == "Author"), None)
                    relative = path.relative_to(root)
                    relative_parent = "" if str(relative.parent) == "." else str(relative.parent).replace("/", "\\")
                    records.append({
                        "Name": relative.name,
                        "Path": "\\" + relative_parent,
                        "Enabled": enabled_node is None or (enabled_node.text or "true").casefold() == "true",
                        "Triggers": trigger_types,
                        "Actions": actions,
                        "Author": author_node.text if author_node is not None else "",
                    })
        except OSError:
            return []
        return records

    def _read_services(self) -> list[AutorunEntry]:
        import winreg

        entries = []
        root = r"SYSTEM\CurrentControlSet\Services"
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, root, 0, winreg.KEY_READ) as services:
                service_count = winreg.QueryInfoKey(services)[0]
                for index in range(service_count):
                    name = winreg.EnumKey(services, index)
                    try:
                        with winreg.OpenKey(services, name, 0, winreg.KEY_READ) as key:
                            start_value = int(winreg.QueryValueEx(key, "Start")[0])
                            if start_value not in (0, 1, 2, 4):
                                continue
                            try:
                                display_name = str(winreg.QueryValueEx(key, "DisplayName")[0])
                            except OSError:
                                display_name = name
                            try:
                                command = str(winreg.QueryValueEx(key, "ImagePath")[0])
                            except OSError:
                                command = ""
                            try:
                                delayed = bool(winreg.QueryValueEx(key, "DelayedAutoStart")[0])
                            except OSError:
                                delayed = False
                            try:
                                account = str(winreg.QueryValueEx(key, "ObjectName")[0])
                            except OSError:
                                account = ""
                    except OSError as error:
                        if getattr(error, "winerror", None) not in (2, 3, 5):
                            self.errors.append(f"Could not read service {name}: {error}")
                        continue
                    executable, arguments = _resolve_reference(command)
                    start_mode = {0: "Boot", 1: "System", 2: "Auto", 4: "Disabled"}[start_value]
                    metadata = {
                        "kind": "service", "service_name": name,
                        "start_mode": start_mode, "delayed": delayed, "state": "Unknown",
                        "account": account,
                    }
                    entries.append(AutorunEntry(
                        entry_id=f"service:{name.casefold()}", name=display_name,
                        category="Services", source=f"Windows Service ({start_mode.lower()} start)",
                        location=rf"HKLM\SYSTEM\CurrentControlSet\Services\{name}", command=command, executable=executable,
                        arguments=arguments, status="Disabled" if start_value == 4 else "Enabled", controllable=True,
                        protected=(name.casefold() in SERVICE_PROTECTION_NAMES), metadata=metadata,
                    ))
        except OSError as error:
            self.errors.append(f"Could not enumerate Windows services: {error}")
        return entries

    def _read_approved_records(self, winreg) -> list[AutorunEntry]:
        hives = {"HKCU": winreg.HKEY_CURRENT_USER, "HKLM": winreg.HKEY_LOCAL_MACHINE}
        entries = []
        for hive, key_path in STARTUP_APPROVED_LOCATIONS:
            try:
                with winreg.OpenKey(hives[hive], key_path, 0, winreg.KEY_READ) as key:
                    for index in range(winreg.QueryInfoKey(key)[1]):
                        name, data, value_type = winreg.EnumValue(key, index)
                        raw = data if isinstance(data, bytes) else b""
                        status = _startup_approved_status(raw)
                        entries.append(AutorunEntry(
                            entry_id=f"approved:{hive}:{key_path}:{name}", name=name,
                            category="Startup Approved", source="Windows Startup Approved status",
                            location=f"{hive}\\{key_path}", command=f"State byte: {raw[0]:02X}" if raw else "Unknown state data",
                            status=status, safety="Unknown", impact="Unknown",
                            controllable=status in ("Enabled", "Disabled"),
                            metadata={"kind": "approved", "hive": hive, "key": key_path,
                                      "value_name": name, "value_type": value_type,
                                      "value_data": _reg_data_to_json(raw)},
                        ))
            except OSError as error:
                if getattr(error, "winerror", None) not in (2, 3):
                    self.errors.append(f"Could not read {hive}\\{key_path}: {error}")
        return entries

    def _read_policies(self, winreg) -> list[AutorunEntry]:
        entries = []
        for hive, key_path in POLICY_LOCATIONS:
            policy_entries = self._registry_value_entries(
                hive, key_path, "Startup-related policy (read only)", "Policies", winreg
            )
            for entry in policy_entries:
                entry.controllable = False
                entry.metadata["kind"] = "policy"
            entries.extend(policy_entries)
        return entries

    def _restore_disabled_records(self) -> list[AutorunEntry]:
        try:
            backups = json.loads(self.settings.value("autorun_restore_records", "{}"))
        except (TypeError, ValueError):
            backups = {}
        if not isinstance(backups, dict):
            return []
        entries = []
        active_ids: set[str] = set()
        # Find active IDs by rescanning only IDs supplied by records is expensive;
        # the caller filters these against the live result after all sources load.
        for entry_id, record in backups.items():
            if not isinstance(record, dict):
                continue
            entries.append(AutorunEntry(
                entry_id=entry_id, name=str(record.get("name", "Disabled entry")),
                category=str(record.get("category", "Startup apps")),
                source=str(record.get("source", "Disabled entry")),
                location=str(record.get("location", "")), command=str(record.get("command", "")),
                executable=str(record.get("executable", "")), arguments=str(record.get("arguments", "")),
                status="Disabled", controllable=True, protected=bool(record.get("protected", False)),
                metadata={**record.get("metadata", {}), "kind": record.get("kind", ""), "disabled_backup": True},
            ))
        return entries

    @staticmethod
    def _deduplicate(entries: list[AutorunEntry]) -> list[AutorunEntry]:
        by_id: dict[str, AutorunEntry] = {}
        for entry in entries:
            by_id.setdefault(entry.entry_id.casefold(), entry)
        values = list(by_id.values())
        fingerprints: dict[str, int] = {}
        for entry in values:
            fingerprint = os.path.normcase(os.path.expandvars(entry.command)).casefold().strip()
            if fingerprint:
                fingerprints[fingerprint] = fingerprints.get(fingerprint, 0) + 1
        for entry in values:
            fingerprint = os.path.normcase(os.path.expandvars(entry.command)).casefold().strip()
            entry.duplicate = bool(fingerprint and fingerprints.get(fingerprint, 0) > 1)
        return values

    def _read_signatures(self, entries: list[AutorunEntry]) -> None:
        paths = sorted({entry.executable for entry in entries if entry.executable and Path(entry.executable).is_file()})
        if not paths:
            return
        script = r"""
$ErrorActionPreference='SilentlyContinue'
$paths = [Console]::In.ReadToEnd() | ConvertFrom-Json
$results = @()
foreach ($p in @($paths)) {
  $sig = Get-AuthenticodeSignature -LiteralPath $p
  $item = Get-Item -LiteralPath $p
  $publisher = ''
  if ($sig.SignerCertificate) { $publisher = $sig.SignerCertificate.GetNameInfo([System.Security.Cryptography.X509Certificates.X509NameType]::SimpleName,$false) }
  if ([string]::IsNullOrWhiteSpace($publisher)) { $publisher = $item.VersionInfo.CompanyName }
  if ([string]::IsNullOrWhiteSpace($publisher)) { $publisher = $item.VersionInfo.ProductName }
  if ([string]::IsNullOrWhiteSpace($publisher)) { $publisher = 'Unknown' }
  $state = if ($sig.Status) { $sig.Status.ToString() } else { 'Unsigned' }
  $results += [pscustomobject]@{Path=$p;Publisher=$publisher;Signature=$state}
}
ConvertTo-Json -InputObject (,$results) -Depth 3 -Compress
"""
        try:
            result = _powershell(script, json.dumps(paths, ensure_ascii=False), timeout=90)
            if result.returncode != 0 or not result.stdout.strip():
                return
            records = json.loads(result.stdout)
            if isinstance(records, dict):
                records = [records]
            else:
                flattened: list[dict[str, Any]] = []
                pending = list(records) if isinstance(records, list) else []
                while pending:
                    item = pending.pop(0)
                    if isinstance(item, dict):
                        flattened.append(item)
                    elif isinstance(item, list):
                        pending[0:0] = item
                records = flattened
            by_path = {os.path.normcase(record.get("Path", "")): record for record in records if isinstance(record, dict)}
            for entry in entries:
                metadata = by_path.get(os.path.normcase(entry.executable))
                if metadata:
                    entry.publisher = str(metadata.get("Publisher") or "Unknown")
                    entry.signature = str(metadata.get("Signature") or "Unknown")
                    if entry.category == "Services" and entry.publisher.casefold().startswith("microsoft"):
                        entry.protected = True
        except (OSError, subprocess.SubprocessError, ValueError, json.JSONDecodeError):
            return

    @staticmethod
    def _assess_entries(entries: list[AutorunEntry]) -> None:
        suspicious_tokens = ("-encodedcommand", " -enc ", "http://", "https://", "\\appdata\\local\\temp\\", "\\temp\\")
        for entry in entries:
            if entry.executable:
                exists = Path(entry.executable).is_file()
                entry.file_exists = "Yes" if exists else "No"
            elif entry.category in ("Policies", "Startup Approved"):
                entry.file_exists = "Not applicable"
            else:
                entry.file_exists = "Unknown"
            command = entry.command.casefold()
            executable_name = Path(entry.executable).name.casefold() if entry.executable else ""
            signed = entry.signature.casefold() == "valid"
            suspicious = (
                entry.file_exists == "No"
                or any(token in command for token in suspicious_tokens)
                or executable_name in {"mshta.exe", "regsvr32.exe"}
                or (executable_name in {"wscript.exe", "cscript.exe", "powershell.exe"}
                    and entry.signature.casefold() != "valid")
            )
            if entry.category in ("Policies", "Startup Approved"):
                entry.safety = "Unknown"
            elif suspicious:
                entry.safety = "Potentially suspicious"
            elif signed and entry.file_exists == "Yes":
                entry.safety = "Safe (heuristic)"
            else:
                entry.safety = "Unknown"
            if entry.category == "Services":
                entry.impact = "High"
            elif "RunOnce" in entry.source:
                entry.impact = "Low"
            elif entry.category == "Scheduled tasks":
                entry.impact = "High" if any("Boot" in str(trigger) for trigger in entry.metadata.get("triggers", [])) else "Medium"
            elif entry.category == "Startup apps":
                entry.impact = "Medium"
            else:
                entry.impact = "Unknown"


class AutorunScanWorker(QThread):
    completed = Signal(object, str, str, object)
    failed = Signal(str)

    def __init__(self, settings: QSettings, parent: QWidget | None = None):
        super().__init__(parent)
        self.settings = settings

    def run(self) -> None:
        try:
            entries, version, architecture, errors = AutorunScanner(self.settings).scan()
            self.completed.emit(entries, version, architecture, errors)
        except Exception as error:
            self.failed.emit(str(error))


class StartupManagerInterface(QWidget):
    COLUMNS = ("Name", "Publisher", "Status", "Impact", "Duplicate", "Executable", "Source / location")

    def __init__(self, parent_window: QWidget):
        super().__init__()
        self.parent_window = parent_window
        self.entries: list[AutorunEntry] = []
        self.worker: AutorunScanWorker | None = None
        self.tables: dict[str, QTableWidget] = {}
        self.visible_entries: dict[str, list[AutorunEntry]] = {}
        self.current_entry: AutorunEntry | None = None
        self._build()
        QTimer.singleShot(0, self.scan)

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 14)
        layout.setSpacing(10)
        layout.addWidget(TitleLabel("Startup Manager"))
        layout.addWidget(CaptionLabel(
            "Review what launches with Windows or at sign-in, where it comes from, and whether its file is signed."
        ))

        info = CardWidget(self)
        info_layout = QVBoxLayout(info)
        info_layout.setContentsMargins(14, 10, 14, 10)
        info_layout.addWidget(BodyLabel(
            "Impact is an estimate, not a measured startup delay. "
            "Services and policy entries are listed separately because changing them can affect Windows. "
            "Startup Approved shows Windows' allow/disable state for startup items. You can enable a known disabled state from its row."
        ))
        layout.addWidget(info)

        toolbar = QHBoxLayout()
        self.scan_button = PrimaryPushButton(FluentIcon.SYNC, "Scan autoruns", self)
        self.scan_button.setFixedHeight(30)
        self.scan_button.clicked.connect(self.scan)
        toolbar.addWidget(self.scan_button)
        self.scan_status = CaptionLabel("Scan to inspect startup entries.", self)
        toolbar.addWidget(self.scan_status, 1)
        layout.addLayout(toolbar)
        self.progress = QProgressBar(self)
        self.progress.setRange(0, 0)
        self.progress.hide()
        layout.addWidget(self.progress)

        self.tabs = QTabWidget(self)
        self.tabs.setObjectName("sectionTabs")
        self.tabs.tabBar().setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        for category in TAB_CATEGORIES:
            table = QTableWidget(self.tabs)
            table.setColumnCount(len(self.COLUMNS))
            table.setHorizontalHeaderLabels(self.COLUMNS)
            table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
            table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
            table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            table.setAlternatingRowColors(True)
            table.setWordWrap(False)
            table.setTextElideMode(Qt.TextElideMode.ElideRight)
            table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            table.horizontalHeader().setSectionsClickable(True)
            table.horizontalHeader().setStretchLastSection(False)
            table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
            table.setColumnWidth(0, 140)
            table.setColumnWidth(1, 130)
            table.setColumnWidth(2, 75)
            table.setColumnWidth(3, 65)
            table.setColumnWidth(4, 65)
            for column in range(5):
                table.horizontalHeader().setSectionResizeMode(column, QHeaderView.ResizeMode.Interactive)
            table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
            table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch)
            table.setToolTip(self._category_description(category))
            table.itemSelectionChanged.connect(lambda cat=category: self._selection_changed(cat))
            self.tables[category] = table
            self.visible_entries[category] = []
            self.tabs.addTab(table, category)
        self.tabs.currentChanged.connect(lambda _index: self._update_actions())
        layout.addWidget(self.tabs, 1)

        detail_card = CardWidget(self)
        detail_layout = QVBoxLayout(detail_card)
        detail_layout.setContentsMargins(14, 10, 14, 10)
        detail_layout.addWidget(StrongBodyLabel("Entry details"))
        self.detail = QLabel("Select an entry to view its details.", detail_card)
        self.detail.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.detail.setWordWrap(True)
        detail_layout.addWidget(self.detail)
        layout.addWidget(detail_card)

        actions = QHBoxLayout()
        self.disable_button = PrimaryPushButton(FluentIcon.PAUSE, "Disable", self)
        self.disable_button.setFixedHeight(30)
        self.disable_button.clicked.connect(lambda: self._apply_selected("disable"))
        self.enable_button = PrimaryPushButton(FluentIcon.PLAY, "Enable / restore", self)
        self.enable_button.setFixedHeight(30)
        self.enable_button.clicked.connect(lambda: self._apply_selected("enable"))
        self.service_button = PushButton(FluentIcon.SETTING, "Disable service…", self)
        self.service_button.setFixedHeight(30)
        self.service_button.clicked.connect(lambda: self._apply_selected("disable_service"))
        self.disable_button.setEnabled(False)
        self.enable_button.setEnabled(False)
        self.service_button.setEnabled(False)
        actions.addWidget(self.disable_button)
        actions.addWidget(self.enable_button)
        actions.addWidget(self.service_button)
        actions.addStretch(1)
        layout.addLayout(actions)

    def scan(self) -> None:
        if self.worker and self.worker.isRunning():
            return
        self.scan_button.setEnabled(False)
        self.progress.show()
        self.scan_status.setText("Reading Windows startup locations…")
        self.worker = AutorunScanWorker(self.parent_window.settings, self)
        self.worker.completed.connect(self._scan_completed)
        self.worker.failed.connect(self._scan_failed)
        self.worker.start()

    @staticmethod
    def _category_description(category: str) -> str:
        return {
            "Startup apps": "Entries from Startup folders and Run/RunOnce registry keys. Known Windows-approved disabled states are reflected here.",
            "Scheduled tasks": "Tasks triggered at Windows startup or user sign-in.",
            "Services": "Windows services configured for boot, system, or automatic start.",
            "Startup Approved": "Windows status records for whether startup items are allowed to run. Enable or disable recognized states here.",
            "Policies": "Startup-related policy entries found in the registry. Read-only.",
        }.get(category, category)

    def _scan_completed(self, entries: list[AutorunEntry], version: str, architecture: str, errors: list[str]) -> None:
        self.entries = entries
        for category, table in self.tables.items():
            subset = [entry for entry in entries if entry.category == category]
            self.visible_entries[category] = subset
            table.setUpdatesEnabled(False)
            table.setSortingEnabled(False)
            table.clearSpans()
            table.setRowCount(max(1, len(subset)))
            tab_index = self.tabs.indexOf(table)
            if tab_index >= 0:
                self.tabs.setTabText(tab_index, f"{category} ({len(subset)})")
            for row, entry in enumerate(subset):
                values = (
                    entry.name, entry.publisher, entry.status, entry.impact,
                    "Yes" if entry.duplicate else "No", entry.executable or "—", entry.location or "—",
                )
                for column, value in enumerate(values):
                    item = QTableWidgetItem(str(value))
                    tooltip = str(value)
                    if column == 5:
                        tooltip = f"Resolved executable: {entry.executable or 'Unknown'}\nCommand: {entry.command or '—'}"
                    elif column == 6:
                        tooltip = f"Source: {entry.source}\nLocation: {entry.location or 'Unknown'}"
                    item.setToolTip(tooltip)
                    item.setData(Qt.ItemDataRole.UserRole, entry.entry_id)
                    table.setItem(row, column, item)
            if not subset:
                unavailable_markers = {
                    "Scheduled tasks": "Could not enumerate Scheduled Tasks",
                    "Services": "Could not enumerate Windows services",
                    "Startup Approved": "Could not read",
                    "Policies": "Could not read",
                }
                marker = unavailable_markers.get(category)
                unavailable = bool(marker and any(marker in error for error in errors))
                message = (
                    "Could not scan this category. See the scan warning for details."
                    if unavailable else "No entries found in this category."
                )
                item = QTableWidgetItem(message)
                item.setFlags(Qt.ItemFlag.ItemIsEnabled)
                table.setItem(0, 0, item)
                table.setSpan(0, 0, 1, len(self.COLUMNS))
            table.setSortingEnabled(True)
            table.setUpdatesEnabled(True)
        self.progress.hide()
        self.scan_button.setEnabled(True)
        self.scan_status.setText(
            f"{version} · {architecture} · {len(entries)} entries" +
            (f" · {len(errors)} read warning(s)" if errors else "")
        )
        self.current_entry = None
        self.detail.setText("Select an entry to view its details.")
        self._update_actions()
        if errors:
            QMessageBox.information(self, "Some startup locations could not be read", "\n".join(errors[:10]))

    def _scan_failed(self, message: str) -> None:
        self.progress.hide()
        self.scan_button.setEnabled(True)
        self.scan_status.setText("Autorun scan failed.")
        QMessageBox.critical(self, "Autorun scan failed", message)

    def _selection_changed(self, category: str) -> None:
        table = self.tables[category]
        rows = table.selectionModel().selectedRows()
        selected_row = rows[0].row() if rows else -1
        selected_item = table.item(selected_row, 0) if selected_row >= 0 else None
        selected_id = selected_item.data(Qt.ItemDataRole.UserRole) if selected_item else None
        self.current_entry = next(
            (entry for entry in self.visible_entries[category] if entry.entry_id == selected_id), None
        )
        entry = self.current_entry
        if entry:
            self.detail.setText(
                f"Name: {entry.name}\nSource: {entry.source}\nLocation: {entry.location}\n"
                f"Command: {entry.command or '—'}\nResolved file: {entry.executable or 'Unknown'}\n"
                f"Arguments: {entry.arguments or '—'}"
            )
        else:
            self.detail.setText("Select an entry to view its details.")
        self._update_actions()

    def _update_actions(self) -> None:
        entry = self.current_entry
        can_change = bool(entry and entry.controllable)
        is_enabled = bool(entry and entry.status == "Enabled")
        is_disabled = bool(entry and entry.status == "Disabled")
        self.disable_button.setEnabled(can_change and is_enabled)
        self.enable_button.setEnabled(can_change and is_disabled)
        can_service = bool(entry and entry.category == "Services" and not entry.protected and is_enabled)
        self.service_button.setEnabled(can_service)

    def _apply_selected(self, operation: str) -> None:
        entry = self.current_entry
        if not entry:
            return
        if entry.category == "Services":
            if operation == "enable":
                answer = QMessageBox.warning(
                    self, "Enable service",
                    f"Enable automatic startup for this service?\n\n{entry.name}\n{entry.location}\n\n"
                    "Changing services can affect Windows or installed software. Administrator access may be required.",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                    QMessageBox.StandardButton.Cancel,
                )
                if answer != QMessageBox.StandardButton.Yes:
                    return
                try:
                    _set_enabled(entry, True, self.parent_window.settings, self)
                except (OSError, ValueError, subprocess.SubprocessError) as error:
                    QMessageBox.critical(self, "Could not restore service", str(error))
                    return
                self.parent_window.log_activity(
                    "Autorun: Service restore", f"{entry.name}; {entry.location}; {entry.command}"
                )
                self.scan()
            else:
                self._service_operation(entry)
            return
        target = entry
        if entry.category == "Startup apps":
            approval_id = entry.metadata.get("approval_entry_id")
            if approval_id:
                target = next((item for item in self.entries if item.entry_id == approval_id), entry)
        try:
            _set_enabled(target, operation == "enable", self.parent_window.settings, self)
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            QMessageBox.critical(self, "Could not update startup entry", str(error))
            return
        self.parent_window.log_activity(
            "Autorun: " + ("Enable / restore" if operation == "enable" else "Disable"),
            f"{entry.name}; {entry.source}; {entry.location}; {entry.command or entry.executable}"
        )
        self.scan()

    def _service_operation(self, entry: AutorunEntry) -> None:
        if entry.protected or entry.publisher.casefold().startswith("microsoft"):
            QMessageBox.warning(
                self, "Protected service",
                "This service appears to be Microsoft or security related. Startup Manager will not change it."
            )
            return
        answer = QMessageBox.warning(
            self, "Advanced service change",
            f"Disable automatic startup for this service?\n\n{entry.name}\n{entry.location}\n\n"
            "Changing services can affect Windows or installed software. Administrator access may be required.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            _set_enabled(entry, False, self.parent_window.settings, self, advanced_service=True)
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            QMessageBox.critical(self, "Could not change service", str(error))
            return
        self.parent_window.log_activity(
            "Autorun: Advanced service disable", f"{entry.name}; {entry.location}; {entry.command}"
        )
        self.scan()


def _load_backups(settings: QSettings) -> dict[str, dict[str, Any]]:
    try:
        value = json.loads(settings.value("autorun_restore_records", "{}"))
    except (TypeError, ValueError):
        value = {}
    return value if isinstance(value, dict) else {}


def _save_backups(settings: QSettings, backups: dict[str, dict[str, Any]]) -> None:
    settings.setValue("autorun_restore_records", json.dumps(backups, ensure_ascii=False))


def _set_approved_enabled(entry: AutorunEntry, enable: bool, settings: QSettings, parent: QWidget,
                          backups: dict[str, dict[str, Any]], qml_mode: bool = False,
                          confirmed: bool = False) -> None:
    import winreg

    metadata = entry.metadata
    hive = winreg.HKEY_CURRENT_USER if metadata.get("hive") == "HKCU" else winreg.HKEY_LOCAL_MACHINE
    access = winreg.KEY_QUERY_VALUE | winreg.KEY_SET_VALUE
    try:
        with winreg.OpenKey(hive, metadata["key"], 0, access) as key:
            current, value_type = winreg.QueryValueEx(key, metadata["value_name"])
            if not isinstance(current, bytes) or not current:
                raise ValueError("Windows returned an unsupported Startup Approved state. Refresh the scan.")
            if enable:
                record = backups.get(entry.entry_id)
                if record and record.get("kind") == "approved":
                    original = _reg_data_from_json(record.get("metadata", {}).get("value_data", {}))
                    expected = bytearray(original)
                    if expected:
                        expected[0] = expected[0] | 0x01
                    if current != bytes(expected):
                        title = "Startup approval changed"
                        message = f"Windows' approval state for {entry.name} changed since it was disabled. Restore the saved state?"
                        if qml_mode and not confirmed:
                            raise StartupConfirmationRequired(title, message)
                        if not qml_mode:
                            answer = QMessageBox.warning(
                                parent, title, message,
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                                QMessageBox.StandardButton.Cancel,
                            )
                            if answer != QMessageBox.StandardButton.Yes:
                                return
                    updated = original
                else:
                    if current[0] not in (0x03, 0x05, 0x07):
                        raise ValueError("This Startup Approved entry is not in a recognized disabled state. Refresh the scan.")
                    updated_bytes = bytearray(current)
                    updated_bytes[0] = updated_bytes[0] - 1
                    updated = bytes(updated_bytes)
            else:
                original = _reg_data_from_json(metadata["value_data"])
                if current != original or value_type != int(metadata["value_type"]):
                    raise ValueError("The Startup Approved value changed after the scan. Refresh and review it again.")
                if current[0] not in (0x02, 0x04, 0x06):
                    raise ValueError("This Startup Approved entry is not in a recognized enabled state. Refresh the scan.")
                backups[entry.entry_id] = _record_entry(entry, "approved")
                _save_backups(settings, backups)
                updated_bytes = bytearray(current)
                updated_bytes[0] = updated_bytes[0] + 1
                updated = bytes(updated_bytes)
            winreg.SetValueEx(key, metadata["value_name"], 0, int(metadata["value_type"]), updated)
            metadata["value_data"] = _reg_data_to_json(updated)
    except OSError as error:
        raise OSError(f"Could not change the Startup Approved state. Appropriate Windows permissions may be required.\n{error}") from error
    if enable:
        backups.pop(entry.entry_id, None)
        _save_backups(settings, backups)


def _record_entry(entry: AutorunEntry, kind: str) -> dict[str, Any]:
    return {
        "name": entry.name, "category": entry.category, "source": entry.source,
        "location": entry.location, "command": entry.command, "executable": entry.executable,
        "arguments": entry.arguments, "protected": entry.protected, "kind": kind,
        "metadata": entry.metadata,
    }


def _set_enabled(entry: AutorunEntry, enable: bool, settings: QSettings, parent: QWidget,
                 advanced_service: bool = False, qml_mode: bool = False,
                 confirmed: bool = False) -> None:
    import winreg

    backups = _load_backups(settings)
    record = backups.get(entry.entry_id)
    kind = entry.metadata.get("kind")
    if kind == "approved":
        _set_approved_enabled(entry, enable, settings, parent, backups, qml_mode, confirmed)
        return
    if enable:
        if kind == "registry" or (record and record.get("kind") == "registry"):
            snapshot = record or _record_entry(entry, "registry")
            metadata = snapshot.get("metadata", {})
            hive = winreg.HKEY_CURRENT_USER if metadata.get("hive") == "HKCU" else winreg.HKEY_LOCAL_MACHINE
            view = int(metadata.get("view", 0))
            access = winreg.KEY_QUERY_VALUE | winreg.KEY_SET_VALUE | view
            try:
                with winreg.OpenKey(hive, metadata["key"], 0, access) as key:
                    try:
                        current, current_type = winreg.QueryValueEx(key, metadata["value_name"])
                    except FileNotFoundError:
                        current = None
                        current_type = None
                    original = _reg_data_from_json(metadata["value_data"])
                    original_type = int(metadata["value_type"])
                    if current is not None and (current != original or current_type != original_type):
                        title = "Startup value changed"
                        message = (f"A newer value now exists for {metadata['value_name']} at {metadata['key']}.\n\n"
                                   "Replace it with the saved original value?")
                        if qml_mode and not confirmed:
                            raise StartupConfirmationRequired(title, message)
                        if not qml_mode:
                            answer = QMessageBox.warning(
                                parent, title, message,
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                                QMessageBox.StandardButton.Cancel,
                            )
                            if answer != QMessageBox.StandardButton.Yes:
                                return
                    winreg.SetValueEx(key, metadata["value_name"], 0, original_type, original)
            except OSError as error:
                raise OSError(f"Could not restore registry startup value. Try running FileSense with appropriate permissions.\n{error}") from error
        elif kind == "startup_folder" or (record and record.get("kind") == "startup_folder"):
            snapshot = record or _record_entry(entry, "startup_folder")
            metadata = snapshot.get("metadata", {})
            source = Path(metadata.get("backup_path", ""))
            destination = Path(metadata.get("original_path", ""))
            if not source.is_file():
                raise FileNotFoundError(f"The saved startup file could not be found: {source}")
            if destination.exists():
                title = "Startup file already exists"
                message = f"A newer file already exists at:\n{destination}\n\nReplace it with the saved file?"
                if qml_mode and not confirmed:
                    raise StartupConfirmationRequired(title, message)
                if not qml_mode:
                    answer = QMessageBox.warning(
                        parent, title, message,
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                        QMessageBox.StandardButton.Cancel,
                    )
                    if answer != QMessageBox.StandardButton.Yes:
                        return
            destination.parent.mkdir(parents=True, exist_ok=True)
            os.replace(source, destination)
        elif kind == "task" or (record and record.get("kind") == "task"):
            task_path = (record or entry.metadata).get("task_path", entry.location)
            _change_task(str(task_path), True)
        elif kind == "service" or (record and record.get("kind") == "service"):
            snapshot = record or _record_entry(entry, "service")
            metadata = snapshot.get("metadata", {})
            _change_service(str(metadata["service_name"]), _service_start_name(
                int(metadata.get("start_value", 2)), bool(metadata.get("delayed", False))
            ))
        else:
            raise ValueError("This entry type cannot be enabled by Startup Manager.")
        backups.pop(entry.entry_id, None)
        _save_backups(settings, backups)
        return

    if not entry.controllable:
        raise ValueError("This entry is informational and cannot be changed here.")
    if kind == "registry":
        metadata = entry.metadata
        hive = winreg.HKEY_CURRENT_USER if metadata.get("hive") == "HKCU" else winreg.HKEY_LOCAL_MACHINE
        try:
            with winreg.OpenKey(hive, metadata["key"], 0,
                                winreg.KEY_QUERY_VALUE | winreg.KEY_SET_VALUE | int(metadata.get("view", 0))) as key:
                current, current_type = winreg.QueryValueEx(key, metadata["value_name"])
                if current != _reg_data_from_json(metadata["value_data"]) or current_type != metadata["value_type"]:
                    raise ValueError("The registry value changed after the scan. Refresh the list and review it again.")
                snapshot = _record_entry(entry, "registry")
                backups[entry.entry_id] = snapshot
                _save_backups(settings, backups)
                winreg.DeleteValue(key, metadata["value_name"])
        except OSError as error:
            raise OSError(f"Could not disable registry startup value. Try running FileSense with appropriate permissions.\n{error}") from error
    elif kind == "startup_folder":
        original = Path(entry.metadata["original_path"])
        if not original.is_file():
            raise FileNotFoundError(f"Startup file is no longer present: {original}")
        if entry.metadata.get("current_path") and Path(entry.metadata["current_path"]) != original:
            raise ValueError("The startup file location changed. Refresh the scan before disabling it.")
        backup_root = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "ProSoft" / "FileSense" / "AutorunRestore"
        backup_root.mkdir(parents=True, exist_ok=True)
        safe_id = hashlib.sha256(entry.entry_id.encode("utf-8")).hexdigest()[:16]
        backup = backup_root / f"{safe_id}_{original.name}"
        if backup.exists():
            backup = backup_root / f"{original.stem}_{os.getpid()}_{original.name}"
        snapshot = _record_entry(entry, "startup_folder")
        snapshot["metadata"]["backup_path"] = str(backup)
        snapshot["metadata"]["original_path"] = str(original)
        backups[entry.entry_id] = snapshot
        _save_backups(settings, backups)
        try:
            shutil.move(str(original), str(backup))
        except OSError:
            backups.pop(entry.entry_id, None)
            _save_backups(settings, backups)
            raise
    elif kind == "task":
        task_path = str(entry.metadata["task_path"])
        backups[entry.entry_id] = _record_entry(entry, "task")
        _save_backups(settings, backups)
        try:
            _change_task(task_path, False)
        except OSError:
            backups.pop(entry.entry_id, None)
            _save_backups(settings, backups)
            raise
    elif kind == "service" and advanced_service:
        if entry.protected or entry.publisher.casefold().startswith("microsoft"):
            raise ValueError("Microsoft and protected services cannot be changed here.")
        service_name = str(entry.metadata["service_name"])
        start_value, delayed = _read_service_start(service_name)
        if start_value not in (0, 1, 2):
            raise ValueError("This service is not configured for automatic startup.")
        snapshot = _record_entry(entry, "service")
        snapshot["metadata"].update({"start_value": start_value, "delayed": delayed})
        backups[entry.entry_id] = snapshot
        _save_backups(settings, backups)
        try:
            _change_service(service_name, "disabled")
        except OSError:
            backups.pop(entry.entry_id, None)
            _save_backups(settings, backups)
            raise
    else:
        raise ValueError("This entry type cannot be changed here.")


def _change_task(task_path: str, enable: bool) -> None:
    result = subprocess.run(
        ["schtasks.exe", "/Change", "/TN", task_path, "/Enable" if enable else "/Disable"],
        capture_output=True, text=True, encoding="oem", errors="replace", timeout=30,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), check=False,
    )
    if result.returncode != 0:
        raise OSError((result.stderr or result.stdout).strip() or "Task Scheduler rejected the change.")


def _read_service_start(service_name: str) -> tuple[int, bool]:
    import winreg
    key_path = rf"SYSTEM\CurrentControlSet\Services\{service_name}"
    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path, 0, winreg.KEY_QUERY_VALUE) as key:
        start = int(winreg.QueryValueEx(key, "Start")[0])
        try:
            delayed = bool(winreg.QueryValueEx(key, "DelayedAutoStart")[0])
        except OSError:
            delayed = False
    return start, delayed


def _service_start_name(start: int, delayed: bool) -> str:
    if start == 0:
        return "boot"
    if start == 1:
        return "system"
    if start == 2:
        return "delayed-auto" if delayed else "auto"
    if start == 3:
        return "demand"
    if start == 4:
        return "disabled"
    raise ValueError(f"Unsupported original service startup value: {start}")


def _change_service(service_name: str, start_type: str) -> None:
    result = subprocess.run(
        ["sc.exe", "config", service_name, "start=", start_type],
        capture_output=True, text=True, encoding="oem", errors="replace", timeout=30,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), check=False,
    )
    if result.returncode != 0:
        raise OSError((result.stderr or result.stdout).strip() or "Service Control Manager rejected the change.")
