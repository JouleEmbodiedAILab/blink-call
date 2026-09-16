"""Backward-compatible settings facade for the Windows watchdog service."""

from blink_call.core.windows_watchdog import WindowsWatchdogManager


class WindowsAutostartManager:
    """Configure BlinkCall's SCM-managed, per-user startup watchdog."""

    @classmethod
    def is_supported(cls) -> bool:
        return WindowsWatchdogManager.is_supported()

    @classmethod
    def set_enabled(cls, enabled: bool) -> tuple[bool, str]:
        return WindowsWatchdogManager.set_enabled(enabled)
