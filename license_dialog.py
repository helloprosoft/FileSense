"""Activation prompt shown when the local trial has expired."""

from __future__ import annotations

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
    QApplication, QDialog, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QPushButton, QVBoxLayout,
)

from app_common import ACCENT_COLOR
from license_manager import activate, machine_fingerprint


class ActivationDialog(QDialog):
    def __init__(self, settings, trial_ended: bool = True):
        super().__init__()
        self.settings = settings
        self.setWindowTitle("Activate FileSense")
        self.setMinimumWidth(520)
        dark = str(settings.value("appearance", "Dark")) == "Dark"
        background = "#171717" if dark else "#F3F2EF"
        surface = "#242424" if dark else "#FAF9F6"
        text = "#F4F4F4" if dark else "#252525"
        muted = "#B9B9B9" if dark else "#66615D"
        border = "#3A3A3A" if dark else "#D8D4CE"
        coffee_orange = "#F28A55"
        coffee_hover = "#FFA06F"
        coffee_pressed = "#D96B38"
        self.setStyleSheet(f"""
            QDialog {{ background: {background}; color: {text}; }}
            QLabel {{ color: {text}; }}
            QLineEdit {{ background: {surface}; color: {text}; border: 1px solid {border};
                border-bottom: 2px solid {border}; border-radius: 8px; padding: 2px 10px; min-height: 30px; max-height: 30px; }}
            QLineEdit:focus {{ border: 1px solid {ACCENT_COLOR}; border-bottom: 2px solid {ACCENT_COLOR}; }}
            QPushButton {{ background: {surface}; color: {text}; border: 1px solid {border};
                border-radius: 8px; padding: 0 12px; min-height: 30px; max-height: 30px; }}
            QPushButton:hover {{ border-color: {ACCENT_COLOR}; }}
            QPushButton#coffeeAction {{ background: {coffee_orange}; color: #241710; border: 1px solid #E87543;
                border-radius: 8px; padding: 0 18px; font-weight: 700; }}
            QPushButton#coffeeAction:hover {{ background: {coffee_hover}; border-color: {coffee_hover}; }}
            QPushButton#coffeeAction:pressed {{ background: {coffee_pressed}; border-color: {coffee_pressed}; }}
            QPushButton#quitAction {{ background: transparent; }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(12)
        title_text = "Your 30-day trial has ended." if trial_ended else "Activate FileSense"
        title = QLabel(title_text, self)
        title.setStyleSheet("font-size: 18px; font-weight: 700;")
        layout.addWidget(title)
        description = QLabel(
            "Request an activation key for this device, then enter it below. "
            "Activation works offline.", self
        )
        description.setStyleSheet(f"color: {muted};")
        layout.addWidget(description)

        layout.addWidget(QLabel("Device activation code", self))
        machine_row = QHBoxLayout()
        self.machine_code = QLineEdit(machine_fingerprint(), self)
        self.machine_code.setReadOnly(True)
        self.machine_code.setFixedHeight(30)
        machine_row.addWidget(self.machine_code, 1)
        copy_button = QPushButton("Copy", self)
        copy_button.setFixedHeight(30)
        self.copy_button = copy_button
        copy_button.clicked.connect(self._copy_machine_code)
        machine_row.addWidget(copy_button)
        layout.addLayout(machine_row)

        layout.addWidget(QLabel("Activation key", self))
        self.key_input = QLineEdit(self)
        self.key_input.setPlaceholderText("Paste your FileSense activation key")
        self.key_input.setClearButtonEnabled(True)
        self.key_input.setFixedHeight(30)
        layout.addWidget(self.key_input)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        quit_button = QPushButton("Quit", self)
        quit_button.setFixedHeight(30)
        quit_button.setObjectName("quitAction")
        quit_button.clicked.connect(self.reject)
        buttons.addWidget(quit_button)
        activate_button = QPushButton("☕  Buy me a Coffee", self)
        activate_button.setFixedHeight(30)
        activate_button.setObjectName("coffeeAction")
        activate_button.clicked.connect(self._activate)
        buttons.addWidget(activate_button)
        layout.addLayout(buttons)

        footer = QLabel(
            f'<span style="color:{ACCENT_COLOR};">✦</span> '
            '<span style="color:#888888;">Built with care.</span> '
            f'<span style="color:{ACCENT_COLOR};">Powered by your support.</span>', self
        )
        footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        footer.setStyleSheet("font-size: 9pt; padding-top: 4px;")
        layout.addWidget(footer)

    def _copy_machine_code(self) -> None:
        QApplication.clipboard().setText(self.machine_code.text())
        self.copy_button.setText("Copied")
        QTimer.singleShot(1400, lambda: self.copy_button.setText("Copy"))

    def _activate(self) -> None:
        success, message = activate(self.settings, self.key_input.text())
        if not success:
            QMessageBox.warning(self, "Activation failed", message)
            return
        QMessageBox.information(self, "Successful activation", "You're officially unlocked! 🎉")
        self.accept()


def ensure_license(settings) -> bool:
    from license_manager import license_status

    if license_status(settings)["state"] != "expired":
        return True
    dialog = ActivationDialog(settings, trial_ended=True)
    return dialog.exec() == QDialog.DialogCode.Accepted
