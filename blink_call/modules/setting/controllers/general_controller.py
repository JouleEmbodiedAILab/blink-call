import logging
import threading

from PySide6.QtCore import QObject, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QMessageBox

from blink_call.core.config_manager import ConfigManager
from blink_call.core.windows_autostart import WindowsAutostartManager
from blink_call.modules.i18n import get_i18n
from blink_call.modules.setting.bindings import ConfigBinder


class GeneralController(QObject):
    autostart_configured = Signal(bool, str)

    def __init__(self, setting_view):
        super().__init__(setting_view)
        self.setting_view = setting_view
        self.vm = setting_view.vm
        self.page = setting_view.general_page
        self._applied_autostart_enabled = bool(self.vm.get_config("startup.enabled"))
        self._pending_autostart_enabled = None
        self.autostart_configured.connect(self._on_autostart_configured)

        self.bind()

    def bind(self):
        ConfigBinder.bind_combo(self.vm, self.page.language_combo, "ui.language")
        ConfigBinder.bind_combo(self.vm, self.page.theme_combo, "ui.theme")
        ConfigBinder.bind_checkbox(self.vm, self.page.autostart_checkbox, "startup.enabled")

        self.page.manual_btn.clicked.connect(self.open_user_manual)
        self.vm.manual_link_text_changed.connect(self.on_manual_link_text_changed)
        self.vm.save_setting.connect(self.apply_autostart)

    def refresh_from_local_config(self):
        language_idx = self.page.language_combo.findData(self.vm.get_config("ui.language"))
        self.page.language_combo.blockSignals(True)
        self.page.language_combo.setCurrentIndex(0 if language_idx < 0 else language_idx)
        self.page.language_combo.blockSignals(False)

        theme_idx = self.page.theme_combo.findData(self.vm.get_config("ui.theme"))
        self.page.theme_combo.blockSignals(True)
        self.page.theme_combo.setCurrentIndex(0 if theme_idx < 0 else theme_idx)
        self.page.theme_combo.blockSignals(False)

        self.page.autostart_checkbox.blockSignals(True)
        self.page.autostart_checkbox.setChecked(bool(self.vm.get_config("startup.enabled")))
        self.page.autostart_checkbox.blockSignals(False)
        self.page.autostart_checkbox.setEnabled(
            WindowsAutostartManager.is_supported() and self._pending_autostart_enabled is None
        )

        i18n = get_i18n(self.vm.get_config("ui.language"))

        self.page.manual_btn.setText(i18n["user_manual"])
        self.page.language_label.setText(i18n["language"])
        self.page.theme_label.setText(i18n["theme"])
        self.page.theme_combo.setItemText(0, i18n["light"])
        self.page.theme_combo.setItemText(1, i18n["dark"])
        self.page.autostart_label.setText(i18n["start_at_login"])
        self.page.autostart_checkbox.setText(i18n["enable"])
        self.page.autostart_status_label.setText(
            "" if WindowsAutostartManager.is_supported() else i18n["windows_only"]
        )
        self.page.disclaimer_title.setText(i18n["disclaimer_title"])
        self.page.disclaimer_text.setText(i18n["disclaimer_text"])
        self.on_manual_link_text_changed("user_manual")

    def on_manual_link_text_changed(self, key: str):
        i18n = get_i18n(self.vm.get_config("ui.language"))
        self.page.manual_label.setText(i18n[key])

    @staticmethod
    def open_user_manual():
        QDesktopServices.openUrl(QUrl("https://JouleEmbodiedAILab.github.io/blink-call/"))

    def apply_autostart(self):
        if not WindowsAutostartManager.is_supported() or self._pending_autostart_enabled is not None:
            return

        enabled = bool(self.vm.get_config("startup.enabled"))
        previous = self._applied_autostart_enabled
        # Saving unrelated settings must not install/remove a service or
        # require administrator privileges when this switch is unchanged.
        if enabled == previous:
            return

        # UAC and SCM startup can take time. Keep the Qt event loop available
        # for camera processing, audio alerts, and window activation.
        self._pending_autostart_enabled = enabled
        self.setting_view.setEnabled(False)
        self.page.autostart_checkbox.setEnabled(False)
        threading.Thread(target=self._configure_autostart, args=(enabled,), daemon=True).start()

    def _configure_autostart(self, enabled):
        try:
            ok, error = WindowsAutostartManager.set_enabled(enabled)
        except Exception as exc:
            logging.getLogger("blink_call.watchdog").exception("watchdog_configuration_failed")
            ok, error = False, str(exc)
        self.autostart_configured.emit(ok, error)

    @Slot(bool, str)
    def _on_autostart_configured(self, ok, error):
        enabled = self._pending_autostart_enabled
        previous = self._applied_autostart_enabled
        self._pending_autostart_enabled = None
        self.setting_view.setEnabled(True)
        self.page.autostart_checkbox.setEnabled(WindowsAutostartManager.is_supported())
        if ok:
            self._applied_autostart_enabled = enabled
            return

        # The settings model is saved before this signal is emitted. Restore
        # the previous persisted value when Windows rejects service setup.
        self.vm.set_config("startup.enabled", previous)
        self.vm.model.local_config.setdefault("startup", {})["enabled"] = previous
        ConfigManager.update_local_config({"startup": {"enabled": previous}})
        self.page.autostart_checkbox.blockSignals(True)
        self.page.autostart_checkbox.setChecked(previous)
        self.page.autostart_checkbox.blockSignals(False)

        i18n = get_i18n(self.vm.get_config("ui.language"))
        QMessageBox.warning(
            self.setting_view,
            i18n["autostart_failed_title"],
            f"{i18n['autostart_failed_text']}\n\n{error}",
        )
