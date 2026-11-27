"""Home screen and overview cards."""

from app_common import *
from PySide6.QtCore import QRectF, QSize, QUrl
from PySide6.QtGui import QBrush, QDesktopServices, QFont, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import QToolButton


SOCIAL_PROFILE_URLS: dict[str, str] = {
    "Instagram": "https://www.instagram.com/ankurtalukdar/",
    "Facebook": "https://www.facebook.com/Ankur4all",
    "LinkedIn": "https://www.linkedin.com/in/ankur-talukdar-b9132545/",
}


def coffee_cup_icon(color: str = "#102321") -> QIcon:
    pixmap = QPixmap(20, 20)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QPen(QColor(color), 1.7, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawRoundedRect(QRectF(3, 9, 10, 7), 1.5, 1.5)
    painter.drawArc(QRectF(11, 9, 6, 6), -80 * 16, 160 * 16)
    painter.drawLine(4, 17, 15, 17)
    painter.drawLine(6, 6, 5, 3)
    painter.drawLine(10, 6, 9, 3)
    painter.end()
    return QIcon(pixmap)


def social_icon(platform: str) -> QIcon:
    pixmap = QPixmap(28, 28)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    if platform == "Instagram":
        gradient = QLinearGradient(2, 26, 26, 2)
        gradient.setColorAt(0.0, QColor("#FCAF45"))
        gradient.setColorAt(0.48, QColor("#DD2A7B"))
        gradient.setColorAt(1.0, QColor("#8134AF"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(gradient))
        painter.drawRoundedRect(QRectF(2, 2, 24, 24), 7, 7)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(Qt.GlobalColor.white, 2))
        painter.drawRoundedRect(QRectF(7, 7, 14, 14), 4, 4)
        painter.drawEllipse(QRectF(10.5, 10.5, 7, 7))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(Qt.GlobalColor.white)
        painter.drawEllipse(QRectF(18, 7.5, 2.5, 2.5))
    elif platform == "Facebook":
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#1877F2"))
        painter.drawEllipse(QRectF(1, 1, 26, 26))
        painter.setPen(Qt.GlobalColor.white)
        painter.setFont(QFont("Segoe UI", 22, QFont.Weight.Bold))
        painter.drawText(QRectF(0, 0, 28, 31), Qt.AlignmentFlag.AlignCenter, "f")
    else:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#0A66C2"))
        painter.drawRoundedRect(QRectF(1, 1, 26, 26), 4, 4)
        painter.setPen(Qt.GlobalColor.white)
        painter.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        painter.drawText(QRectF(0, 0, 28, 28), Qt.AlignmentFlag.AlignCenter, "in")
    painter.end()
    return QIcon(pixmap)


class HomeInterface(QWidget):
    def __init__(self, window: "OrganizerWindow"):
        super().__init__()
        self.window = window
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 26, 32, 22)
        layout.setSpacing(16)

        top = QHBoxLayout()
        top.addStretch(1)
        license_info = getattr(window, "license_info", {})
        self.license_label = CaptionLabel(self)
        self.activate_button = QPushButton("Buy me a Coffee", self)
        self.activate_button.setIcon(coffee_cup_icon("#241710"))
        self.activate_button.setIconSize(QSize(18, 18))
        self.activate_button.setObjectName("homeCoffeeAction")
        self.activate_button.setStyleSheet("""
            QPushButton#homeCoffeeAction {
                background-color: #F28A55;
                color: #241710;
                border: 1px solid #E87543;
                border-radius: 8px;
                padding: 0 14px;
                font-weight: 600;
            }
            QPushButton#homeCoffeeAction:hover { background-color: #FFA06F; border-color: #FFA06F; }
            QPushButton#homeCoffeeAction:pressed { background-color: #D96B38; border-color: #D96B38; }
        """)
        self.activate_button.setFixedHeight(30)
        self.activate_button.clicked.connect(window.show_activation_dialog)
        top.addWidget(self.license_label)
        top.addWidget(self.activate_button)
        self.refresh_license_status(license_info)
        appearance_label = CaptionLabel("Appearance")
        top.addWidget(appearance_label)
        self.appearance = NoScrollbarComboBox(self)
        self.appearance.addItems(["Light", "Dark"])
        self.appearance.setCurrentText(window.appearance)
        self.appearance.setFixedWidth(105)
        self.appearance.currentTextChanged.connect(window.set_appearance)
        top.addWidget(self.appearance)
        layout.addLayout(top)

        hero = CardWidget(self)
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(24, 20, 24, 20)
        title_row = QHBoxLayout()
        logo = QLabel(hero)
        logo.setPixmap(QPixmap(str(resource_path("assets/FSICO.png"))).scaled(
            42, 42, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
        ))
        logo.setFixedSize(42, 42)
        title_row.addWidget(logo)
        title_row.addWidget(TitleLabel("FileSense"))
        title_row.addStretch(1)
        hero_layout.addLayout(title_row)
        hero_layout.addWidget(SubtitleLabel("One smarter way to manage your PC."))
        layout.addWidget(hero)

        cards = QHBoxLayout()
        cards.setSpacing(16)
        cards.addWidget(self._action_card(
            FluentIcon.FOLDER, "File Organizer",
            "Sort files into categories or create custom organization rules.",
            "Organize files", lambda: window.switchTo(window.categories_page)))
        cards.addWidget(self._action_card(
            FluentIcon.PIE_SINGLE, "Storage Analyzer",
            "Explore folder sizes and see where your drive space is used.",
            "Analyze storage", lambda: window.switchTo(window.storage_page)))
        cards.addWidget(self._action_card(
            FluentIcon.SEARCH, "File Search & Finder",
            "Find files by name, extension, type, size, and date.",
            "Search files", lambda: window.switchTo(window.file_search_page)))
        layout.addLayout(cards)

        more_cards = QHBoxLayout()
        more_cards.setSpacing(16)
        more_cards.addWidget(self._action_card(
            FluentIcon.COPY, "Duplicate Finder",
            "Find repeated file and folder names, then choose which entry to keep.",
            "Find duplicates", lambda: window.switchTo(window.duplicates_page)))
        more_cards.addWidget(self._action_card(
            FluentIcon.DELETE, "Junk Cleaner",
            "Review temporary files and other cleanup candidates by category.",
            "Review cleanup", lambda: window.switchTo(window.junk_cleaner_page)))
        more_cards.addWidget(self._action_card(
            FluentIcon.POWER_BUTTON, "Startup Manager",
            "Review and manage apps that launch with Windows.",
            "Review startup items", lambda: window.switchTo(window.autorun_page)))
        layout.addLayout(more_cards)
        layout.addStretch(1)
        footer = CaptionLabel(self)
        footer.setTextFormat(Qt.TextFormat.RichText)
        footer.setText('Crafted by <span style="color:#F28A55;"><b>Ankur</b></span> © <b>Prosoft</b>')
        footer.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(footer)

    def refresh_license_status(self, status: dict[str, object] | None = None) -> None:
        status = status or getattr(self.window, "license_info", {})
        if status.get("state") == "activated":
            self.license_label.setText("✓ Activated")
            self.license_label.setStyleSheet(f"color: {ACCENT_COLOR}; font-weight: 600;")
            self.activate_button.hide()
        else:
            self.license_label.setText(
                f"Trial · {status.get('days_remaining', 0)} days remaining"
            )
            self.license_label.setStyleSheet("")
            self.activate_button.show()

    def _action_card(self, icon, title: str, description: str, button_text: str, callback) -> CardWidget:
        card = CardWidget(self)
        card.setBorderRadius(12)
        box = QVBoxLayout(card)
        box.setContentsMargins(20, 18, 20, 18)
        box.setSpacing(10)
        box.addWidget(StrongBodyLabel(title))
        desc = BodyLabel(description)
        desc.setWordWrap(True)
        desc.setFixedHeight(42)
        desc.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        box.addWidget(desc)
        button = PrimaryPushButton(icon, button_text, card)
        button.clicked.connect(callback)
        box.addWidget(button, alignment=Qt.AlignmentFlag.AlignLeft)
        box.addStretch(1)
        return card

    def show_about(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("About FileSense")
        dialog.setMinimumWidth(480)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(24, 22, 24, 18)
        layout.setSpacing(0)

        title = QLabel("FileSense", dialog)
        title.setFont(QFont("Segoe UI", 18, QFont.Weight.DemiBold))
        title.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(title)
        layout.addSpacing(4)
        tagline = BodyLabel(dialog)
        tagline.setTextFormat(Qt.TextFormat.RichText)
        tagline.setText("<b>One smarter way to manage your PC.</b>")
        tagline.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        layout.addWidget(tagline)
        layout.addSpacing(6)
        description = BodyLabel(
            "Organize files, find duplicates, analyze storage, manage startup items, "
            "clean junk files, and search across your folders.", dialog
        )
        description.setWordWrap(True)
        description.setFont(QFont("Segoe UI", 10, QFont.Weight.Normal))
        layout.addWidget(description)
        layout.addSpacing(24)

        bottom_row = QHBoxLayout()
        brand_stack = QVBoxLayout()
        brand_stack.setContentsMargins(0, 0, 0, 0)
        brand_stack.setSpacing(3)
        crafted = CaptionLabel(dialog)
        crafted.setTextFormat(Qt.TextFormat.RichText)
        crafted.setFont(QFont("Segoe UI", 10, QFont.Weight.Normal))
        crafted.setText('Crafted by <span style="color:#F28A55;"><b>Ankur</b></span> © <b>Prosoft</b>')
        brand_stack.addWidget(crafted)

        if SOCIAL_PROFILE_URLS:
            social_row = QHBoxLayout()
            social_row.setContentsMargins(0, 0, 0, 0)
            social_row.setSpacing(3)
            social_row.addWidget(StrongBodyLabel("Follow Me", dialog))
            social_row.addSpacing(7)
            for platform, url in SOCIAL_PROFILE_URLS.items():
                link = QToolButton(dialog)
                link.setIcon(social_icon(platform))
                link.setIconSize(QSize(24, 24))
                link.setFixedSize(30, 30)
                link.setAutoRaise(True)
                link.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
                link.setAccessibleName(platform)
                link.setToolTip(platform)
                link.setStyleSheet("QToolButton { background: transparent; border: none; padding: 0; } QToolButton:hover { background: rgba(127,127,127,35); border-radius: 15px; }")
                link.clicked.connect(lambda _checked=False, target=url: QDesktopServices.openUrl(QUrl(target)))
                social_row.addWidget(link)
            brand_stack.addLayout(social_row)

        bottom_row.addLayout(brand_stack)
        bottom_row.addStretch(1)
        close = PushButton("Close", dialog)
        close.clicked.connect(dialog.accept)
        bottom_row.addWidget(close, alignment=Qt.AlignmentFlag.AlignVCenter)
        layout.addLayout(bottom_row)
        dialog.exec()


