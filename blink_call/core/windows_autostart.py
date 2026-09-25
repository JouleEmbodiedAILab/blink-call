"""Backward-compatible settings facade for the Windows watchdog service."""

from blink_call.core.windows_watchdog import WindowsWatchdogManager


class WindowsAutostartManager:
    """Configure BlinkCall's machine-wide, per-session startup watchdog."""

    @classmethod
    def is_supported(cls) -> bool:
        return (
            WindowsWatchdogManager.is_supported()
            and WindowsWatchdogManager._packaged_executable() is not None
        )

    @classmethod
    def set_enabled(cls, enabled: bool) -> tuple[bool, str]:
        return WindowsWatchdogManager.configure(enabled)

    @classmethod
    def get_enabled(cls) -> bool:
        return cls.is_supported() and WindowsWatchdogManager.get_startup_policy_enabled()
