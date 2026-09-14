from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
)

from blink_call.widget import HDividerLine


class GeneralPage:
    def __init__(self, content_stack):
        scroll = QScrollArea()
        scroll.setObjectName("settingRightScroll")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content_stack.addWidget(scroll)

        page = QFrame()
        page.setObjectName("settingContentPage")
        page.setMinimumWidth(700)
        scroll.setWidget(page)

        layout = QVBoxLayout(page)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(16)

        manual_row = QHBoxLayout()
        manual_row.setSpacing(16)
        self.manual_label = QLabel("User Manual")
        self.manual_label.setObjectName("settingSubSectionTitle")
        self.manual_btn = QPushButton("User Manual")
        self.manual_btn.setObjectName("settingUserManualBtn")
        self.manual_btn.setFixedSize(220, 36)
        manual_row.addWidget(self.manual_label)
        manual_row.addStretch()
        manual_row.addWidget(self.manual_btn)
        layout.addLayout(manual_row)

        layout.addWidget(HDividerLine())

        language_row = QHBoxLayout()
        language_row.setSpacing(16)
        self.language_label = QLabel("Language")
        self.language_label.setObjectName("settingSubSectionTitle")
        self.language_combo = QComboBox()
        self.language_combo.addItem("中文", "zh")
        self.language_combo.addItem("English", "en")
        self.language_combo.setFixedSize(220, 40)
        language_row.addWidget(self.language_label)
        language_row.addStretch()
        language_row.addWidget(self.language_combo)
        layout.addLayout(language_row)

        layout.addWidget(HDividerLine())

        theme_row = QHBoxLayout()
        theme_row.setSpacing(16)
        self.theme_label = QLabel("Theme")
        self.theme_label.setObjectName("settingSubSectionTitle")
        self.theme_combo = QComboBox()
        self.theme_combo.setFixedSize(220, 40)
        self.theme_combo.addItem("Light", "light")
        self.theme_combo.addItem("Dark", "dark")
        theme_row.addWidget(self.theme_label)
        theme_row.addStretch()
        theme_row.addWidget(self.theme_combo)
        layout.addLayout(theme_row)

        layout.addWidget(HDividerLine())

        autostart_row = QHBoxLayout()
        autostart_row.setSpacing(16)
        self.autostart_label = QLabel("Start automatically")
        self.autostart_label.setObjectName("settingSubSectionTitle")
        self.autostart_checkbox = QCheckBox("Enable")
        self.autostart_checkbox.setFixedWidth(220)
        self.autostart_status_label = QLabel("")
        self.autostart_status_label.setWordWrap(True)
        autostart_row.addWidget(self.autostart_label)
        autostart_row.addStretch()
        autostart_row.addWidget(self.autostart_checkbox)
        autostart_row.addWidget(self.autostart_status_label)
        layout.addLayout(autostart_row)

        layout.addWidget(HDividerLine())
        layout.addStretch()
