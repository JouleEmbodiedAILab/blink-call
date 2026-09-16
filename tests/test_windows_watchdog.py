"""Platform-neutral checks for the Windows watchdog configuration helpers."""

from types import SimpleNamespace
import unittest

from blink_call.core.windows_watchdog import (
    WATCHDOG_SERVICE_ARGUMENT,
    WATCHDOG_SUPERVISED_ARGUMENT,
    WATCHDOG_USER_EXIT_CODE,
    WindowsWatchdogManager,
    WindowsWatchdogService,
)


class WindowsWatchdogTests(unittest.TestCase):
    def test_legacy_task_not_found_is_not_an_error(self):
        result = SimpleNamespace(stdout="", stderr="ERROR: The system cannot find the file specified.")

        self.assertTrue(WindowsWatchdogManager._legacy_task_not_found(result))

    def test_service_already_running_detection(self):
        result = SimpleNamespace(stdout="[SC] StartService FAILED 1056", stderr="")

        self.assertTrue(WindowsWatchdogManager._service_already_running(result))

    def test_service_argument_constants_are_distinct(self):
        self.assertNotEqual(WATCHDOG_SERVICE_ARGUMENT, WATCHDOG_SUPERVISED_ARGUMENT)
        self.assertNotEqual(WATCHDOG_USER_EXIT_CODE, 0)

    def test_non_windows_service_entrypoint_is_safe(self):
        if WindowsWatchdogManager.is_supported():
            self.skipTest("This assertion is only for non-Windows test runners.")
        self.assertEqual(WindowsWatchdogService().run(), 1)


if __name__ == "__main__":
    unittest.main()
