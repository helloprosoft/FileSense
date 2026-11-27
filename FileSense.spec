# -*- mode: python ; coding: utf-8 -*-
"""Curated, reproducible onedir build for FileSense 2.0.0."""

from pathlib import Path
import os
import sys

ROOT = Path(SPECPATH)
PYTHON = Path(sys.executable)
SITE_PACKAGES = PYTHON.parent.parent / "Lib" / "site-packages"
PYSIDE_QML = SITE_PACKAGES / "PySide6" / "qml"

# Qt Quick modules imported by qml/*.qml. Exclude unrelated Qt components,
# examples, designer metadata, and the unused control themes.
EXTRA_QML_DIRS = (
    "Qt/labs/folderlistmodel",
    "QtQml/Models",
    "QtQml/WorkerScript",
    "QtQuick/Controls",
    "QtQuick/Controls/Basic",
    "QtQuick/Controls/Fusion",
    "QtQuick/Controls/impl",
    "QtQuick/Dialogs",
    "QtQuick/Dialogs/quickimpl",
    "QtQuick/Effects",
    "QtQuick/Layouts",
    "QtQuick/Shapes",
    "QtQuick/Templates",
    "QtQuick/Window",
)
SKIP_DIR_NAMES = {
    "+Imagine", "+Material", "+Universal", "designer", "doc", "docs",
    "examples", "test", "tests", "__pycache__",
}
SKIP_SUFFIXES = {".qmltypes", ".pyc", ".pyo"}


def qml_datas():
    result = []
    # Root plugin descriptors/binaries required by the imported modules.
    for relative in ("QtQml", "QtQuick", "QtQuick/Controls"):
        base = PYSIDE_QML / relative
        if base.is_dir():
            for name in base.iterdir():
                if name.is_file() and name.suffix.lower() not in SKIP_SUFFIXES:
                    destination = "PySide6/qml/" + name.relative_to(PYSIDE_QML).parent.as_posix()
                    result.append((str(name), destination))
    for relative in EXTRA_QML_DIRS:
        base = PYSIDE_QML / relative
        if not base.is_dir():
            continue
        for current, dirs, files in os.walk(base):
            dirs[:] = [name for name in dirs if name not in SKIP_DIR_NAMES]
            for name in files:
                source = Path(current) / name
                if source.suffix.lower() in SKIP_SUFFIXES:
                    continue
                destination = "PySide6/qml/" + source.relative_to(PYSIDE_QML).parent.as_posix()
                result.append((str(source), destination))
    return result


datas = [(str(ROOT / "assets"), "assets"), (str(ROOT / "qml"), "qml"),
         (str(ROOT / "README.md"), ".")]
datas += qml_datas()
binaries = []
hiddenimports = []

excluded_modules = [
    "qfluentwidgets", "PySide6.Qt3DCore", "PySide6.Qt3DRender", "PySide6.Qt3DInput",
    "PySide6.Qt3DAnimation", "PySide6.Qt3DExtras", "PySide6.QtCharts",
    "PySide6.QtDataVisualization", "PySide6.QtGraphs", "PySide6.QtGraphsWidgets",
    "PySide6.QtLocation", "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets",
    "PySide6.QtQuick3D", "PySide6.QtQuickWidgets", "PySide6.QtWebChannel",
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebSockets",
    "PySide6.QtWebView", "PySide6.QtPositioning", "PySide6.QtDBus", "PySide6.QtDesigner",
    "PySide6.QtHelp", "PySide6.QtHttpServer", "PySide6.QtNfc", "PySide6.QtPrintSupport",
    "PySide6.QtRemoteObjects", "PySide6.QtScxml", "PySide6.QtSensors", "PySide6.QtSerialPort",
    "PySide6.QtSql", "PySide6.QtStateMachine", "PySide6.QtTextToSpeech", "PySide6.QtTest",
]

a = Analysis(
    [str(ROOT / "FileSense.py")], pathex=[str(ROOT)], binaries=binaries, datas=datas,
    hiddenimports=hiddenimports, hookspath=[str(ROOT / "pyinstaller_hooks")], hooksconfig={}, runtime_hooks=[],
    excludes=excluded_modules, noarchive=False, optimize=1,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True, name="FileSense", debug=False,
    bootloader_ignore_signals=False, strip=False, upx=True, console=False,
    disable_windowed_traceback=False, argv_emulation=False, target_arch=None,
    codesign_identity=None, entitlements_file=None, version=str(ROOT / "version_info.txt"),
    icon=[str(ROOT / "assets" / "FSICO.ico")],
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=True, upx_exclude=[], name="FileSense")
