"""Qt Quick application entry point for FileSense 2.0.0."""

from __future__ import annotations

import sys
import os
from pathlib import Path

os.environ["FILESENSE_QML_RUNTIME"] = "1"

from PySide6.QtCore import QUrl
from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle

from .app_common import resource_path
from .qml_backend import FileSenseBackend

APP_VERSION = "2.0.0"


def main() -> int:
    # Main.qml provides its own control indicators, content items, and backgrounds.
    # Select a style that supports custom Qt Quick Controls before creating the app.
    QQuickStyle.setStyle("Fusion")
    app = QGuiApplication(sys.argv)
    app.setApplicationName("FileSense")
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName("ProSoft")
    app.setWindowIcon(QIcon(str(resource_path("assets/FSICO.png"))))

    backend = FileSenseBackend()
    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("fileSense", backend)
    qml_path = resource_path("qml/Main.qml")
    engine.load(QUrl.fromLocalFile(str(qml_path)))
    if not engine.rootObjects():
        return 1
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
