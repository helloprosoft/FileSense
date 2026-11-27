"""Avoid PyInstaller's default all-QML-modules collection.

FileSense.spec provides only the Qt Quick QML runtime modules used by the
application. Keep PyInstaller's normal Qt dependency discovery for binaries
and Python imports without copying every installed QML module.
"""

from PyInstaller.utils.hooks.qt import add_qt6_dependencies

hiddenimports, binaries, datas = add_qt6_dependencies(__file__)
