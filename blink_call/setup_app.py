import sys
from pathlib import Path

from blink_call.core.windows_watchdog import (
    WATCHDOG_CONFIGURE_ARGUMENT,
    WATCHDOG_SERVICE_ARGUMENT,
    WATCHDOG_USER_EXIT_CODE,
    run_watchdog_configuration,
    run_watchdog_service,
)

if __name__ == "__main__":
    # These processes must bypass both Qt initialization and the GUI mutex.
    # In particular, the UAC helper must not activate a non-elevated instance.
    if sys.argv[1:2] == [WATCHDOG_SERVICE_ARGUMENT]:
        sys.exit(run_watchdog_service())
    if sys.argv[1:2] == [WATCHDOG_CONFIGURE_ARGUMENT]:
        sys.exit(run_watchdog_configuration(sys.argv[2:]))

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


def create_app(app=None):
    if app is None:
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
    app.aboutToQuit.connect(main_window.shutdown)
    nav = Navigation(main_window)

    # Add pages
    create_page("home", main_window, nav)
    DI.get("home_vm").setting_vm.language_changed.connect(main_window.set_ui_language)
    DI.get("home_vm").setting_vm.theme_changed.connect(
        lambda value: theme.load(f'{"dark" if str(value).lower() == "dark" else "light"}.qss')
    )

    # Default page
    nav.to("home")

    app.setQuitOnLastWindowClosed(not main_window.close_to_tray)

    return app, main_window


if __name__ == "__main__":
    app = QApplication(sys.argv)
    single_instance = None
    if sys.platform == "win32":
        from blink_call.core.windows_single_instance import WindowsSingleInstance

        single_instance = WindowsSingleInstance(app)
        if not single_instance.acquire():
            sys.exit(0)

    app, window = create_app(app)
    if "--background" in app.arguments() and window.tray_available:
        window.hide()
    else:
        window.show_window()
    if single_instance is not None:
        single_instance.bind_window(window)
    try:
        exit_code = app.exec()
    finally:
        if single_instance is not None:
            single_instance.close()
    # The service also adopts GUI processes started manually before enablement.
    if sys.platform == "win32" and window.user_requested_exit:
        exit_code = WATCHDOG_USER_EXIT_CODE
    sys.exit(exit_code)
