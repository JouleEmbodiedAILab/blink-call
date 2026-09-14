from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QMenu,
    QStackedWidget,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from blink_call.core.config_manager import ConfigManager
from blink_call.modules.i18n import get_i18n
from blink_call.core.resource_path import get_resource_path


class MainWindow(QWidget):
    WINDOW_TITLE = {
        "zh": "\u7728\u773c\u547c\u53eb",
        "en": "Blink Call",
    }

    def __init__(self):
        super().__init__()
        language = self._load_ui_language()
        self.resize(1200, 800)
        self.setMinimumSize(800, 600)

        self.stack = QStackedWidget()
        self.views = {}
        self._allow_close = False
        self.tray_icon = None
        self.tray_show_action = None
        self.tray_exit_action = None
        self._setup_system_tray()
        self.set_ui_language(language)

        layout = QVBoxLayout(self)
        layout.addWidget(self.stack)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

    @staticmethod
    def _load_ui_language():
        local_ui = ConfigManager.get_local_config().get("ui") or {}
        default_ui = ConfigManager.get_default_config().get("ui") or {}
        return local_ui.get("language", default_ui.get("language", "zh"))

    def set_ui_language(self, language):
        title_base = self.WINDOW_TITLE.get(language, self.WINDOW_TITLE["zh"])
        self.setWindowTitle(f"{title_base} v{self.get_version()}")
        if self.tray_icon is not None:
            i18n = get_i18n(language)
            self.tray_icon.setToolTip(title_base)
            self.tray_show_action.setText(i18n["show_window"])
            self.tray_exit_action.setText(i18n["exit"])

    def add_page(self, name, view):
        self.views[name] = view
        self.stack.addWidget(view)

    def navigate(self, name):
        view = self.views[name]
        vm = getattr(view, "vm", None)

        if hasattr(vm, "on_page_enter"):
            vm.on_page_enter()
        self.stack.setCurrentWidget(view)

    def closeEvent(self, event):
        if (
            not self._allow_close
            and self.tray_icon is not None
            and self.tray_icon.isVisible()
            and not event.spontaneous()
        ):
            self.hide()
            event.ignore()
            return

        for view in self.views.values():
            vm = getattr(view, "vm", None)
            if hasattr(vm, "stop_all"):
                vm.stop_all()
        if self.tray_icon is not None:
            self.tray_icon.hide()
        super().closeEvent(event)

    @property
    def tray_available(self):
        return self.tray_icon is not None

    def _setup_system_tray(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return

        icon_path = get_resource_path("assets", "icons", "app_icon.ico")
        self.tray_icon = QSystemTrayIcon(QIcon(str(icon_path)), self)
        self.tray_menu = QMenu(self)
        self.tray_show_action = QAction(self)
        self.tray_exit_action = QAction(self)
        self.tray_show_action.triggered.connect(self.show_window)
        self.tray_exit_action.triggered.connect(self.exit_application)
        self.tray_menu.addAction(self.tray_show_action)
        self.tray_menu.addSeparator()
        self.tray_menu.addAction(self.tray_exit_action)
        self.tray_icon.setContextMenu(self.tray_menu)
        self.tray_icon.activated.connect(self._on_tray_activated)
        self.tray_icon.show()

    def _on_tray_activated(self, reason):
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self.show_window()

    def show_window(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def exit_application(self):
        self._allow_close = True
        self.close()
        application = QApplication.instance()
        if application is not None:
            application.quit()

    @staticmethod
    def get_version():
        with open("VERSION", encoding="utf-8") as f:
            version = f.read().strip()

        return version
