import sys
from pathlib import Path

from PySide6.QtCore import QStandardPaths
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from blink_call.core.config_manager import ConfigManager
from blink_call.core.dependency_injection import DI
from blink_call.core.logging_setup import configure_app_logging
from blink_call.core.navigation import Navigation
from blink_call.core.theme_manager import ThemeManager
from blink_call.main_window import MainWindow
from blink_call.modules import MODULES_REGISTRY
from blink_call.core.resource_path import get_resource_path


def create_page(name, main_window, nav):
    _module = MODULES_REGISTRY[name]

    # Dependency Injection
    DI.register(name + "_model", _module["model"]())
    DI.register(name + "_vm", _module["vm"](DI.get(name + "_model")))

    # Create views
    view = _module["view"](DI.get(name + "_vm"), nav)

    # Add pages
    main_window.add_page(name, view)


def create_app():
    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon(str(get_resource_path("assets", "icons", "eye.png"))))

    app_data_dir = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation)
    if not app_data_dir:
        app_data_dir = QStandardPaths.writableLocation(QStandardPaths.TempLocation)
    configure_app_logging(Path(app_data_dir) / "blink_call" / "logs")

    # Load theme
    theme = ThemeManager(app, qss_dir=str(get_resource_path("assets", "qss")))
    ui_config = ConfigManager.get_local_config().get("ui") or {}
    theme_name = str(ui_config.get("theme") or "light").strip().lower()
    if theme_name not in {"light", "dark"}:
        theme_name = "light"
    theme.load(f"{theme_name}.qss")

    # Initialize the main window
    main_window = MainWindow()
    nav = Navigation(main_window)

    # Add pages
    create_page("home", main_window, nav)
    DI.get("home_vm").setting_vm.language_changed.connect(main_window.set_ui_language)
    DI.get("home_vm").setting_vm.theme_changed.connect(
        lambda value: theme.load(f'{"dark" if str(value).lower() == "dark" else "light"}.qss')
    )

    # Default page
    nav.to("home")

    if main_window.tray_available:
        app.setQuitOnLastWindowClosed(False)

    return app, main_window


if __name__ == "__main__":
    app, window = create_app()
    if "--background" in app.arguments() and window.tray_available:
        window.hide()
    else:
        window.show()
    sys.exit(app.exec())
