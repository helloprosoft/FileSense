"""Small desktop utility for issuing offline FileSense activation keys."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QPushButton, QTextEdit, QVBoxLayout, QWidget,
)

from activation_key_tool import generate_activation_key


class ActivationKeyGenerator(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("FileSense Activation Key Generator")
        self.setMinimumSize(580, 430)
        self.resize(680, 480)
        icon_path = Path(__file__).resolve().parent / "assets" / "FSICO.png"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(10)
        heading = QLabel("Generate an offline activation key", self)
        heading.setFont(QFont("Segoe UI", 15, QFont.Weight.DemiBold))
        layout.addWidget(heading)
        layout.addWidget(QLabel("Enter the device code shown in FileSense.", self))

        layout.addWidget(QLabel("Device code", self))
        self.machine_code = QLineEdit(self)
        self.machine_code.setPlaceholderText("FS1-XXXXXXXXXXXXXXXX")
        layout.addWidget(self.machine_code)

        layout.addWidget(QLabel("Private signing key", self))
        key_row = QHBoxLayout()
        default_key = Path(__file__).resolve().parent / "developer_keys" / "FileSense_activation_private.pem"
        self.private_key = QLineEdit(str(default_key), self)
        key_row.addWidget(self.private_key, 1)
        browse = QPushButton("Browse…", self)
        browse.setFixedHeight(30)
        browse.clicked.connect(self._browse_key)
        key_row.addWidget(browse)
        layout.addLayout(key_row)

        self.generate_button = QPushButton("Generate activation key", self)
        self.generate_button.setFixedHeight(30)
        self.generate_button.clicked.connect(self._generate)
        layout.addWidget(self.generate_button, alignment=Qt.AlignmentFlag.AlignLeft)

        output_row = QHBoxLayout()
        output_row.addWidget(QLabel("Activation key", self))
        output_row.addStretch(1)
        self.copy_button = QPushButton("Copy key", self)
        self.copy_button.setFixedHeight(30)
        self.copy_button.setEnabled(False)
        self.copy_button.clicked.connect(self._copy_key)
        output_row.addWidget(self.copy_button)
        layout.addLayout(output_row)

        self.output = QTextEdit(self)
        self.output.setReadOnly(True)
        self.output.setPlaceholderText("Generated key will appear here.")
        self.output.setMinimumHeight(100)
        layout.addWidget(self.output, 1)

        self.status = QLabel("The private key stays on this computer. Share only the generated activation key.", self)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

    def _browse_key(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select FileSense private signing key", self.private_key.text(),
            "PEM private keys (*.pem);;All files (*.*)",
        )
        if path:
            self.private_key.setText(path)

    def _generate(self) -> None:
        try:
            key = generate_activation_key(
                self.machine_code.text(), Path(self.private_key.text().strip())
            )
        except (OSError, ValueError, TypeError) as error:
            QMessageBox.warning(self, "Could not generate key", str(error))
            return
        self.output.setPlainText(key)
        self.copy_button.setEnabled(True)
        self.status.setText("Key generated. Copy it and send it to the user for this device.")

    def _copy_key(self) -> None:
        QApplication.clipboard().setText(self.output.toPlainText())
        self.status.setText("Activation key copied to the clipboard.")


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("FileSense Activation Key Generator")
    app.setFont(QFont("Segoe UI", 10))
    window = ActivationKeyGenerator()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
