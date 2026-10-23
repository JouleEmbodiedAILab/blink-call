"""Windows service watchdog for keeping BlinkCall available in user sessions.

The GUI application is deliberately not a Windows service: Windows services run
in Session 0 and cannot own a user's tray icon or windows. Instead, this module
installs a small service from the same executable. The service starts the GUI
in each active user session and restarts it after an unexpected exit. The
Service Control Manager (SCM) separately restarts the watchdog itself.
"""

from __future__ import annotations

import ctypes
import json
import locale
import logging
import os
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from ctypes import wintypes
from dataclasses import dataclass
from logging.handlers import RotatingFileHandler
from pathlib import Path


logger = logging.getLogger("blink_call.watchdog")

WATCHDOG_SERVICE_ARGUMENT = "--watchdog-service"
WATCHDOG_CONFIGURE_ARGUMENT = "--watchdog-configure"
WATCHDOG_SUPERVISED_ARGUMENT = "--watchdog-supervised"
WATCHDOG_USER_EXIT_CODE = 0x4243


# Service and process constants from Win32 headers. Keeping the definitions
# here avoids a pywin32 runtime dependency in the standalone application.
SERVICE_WIN32_OWN_PROCESS = 0x00000010
SERVICE_START_PENDING = 0x00000002
SERVICE_STOP_PENDING = 0x00000003
SERVICE_RUNNING = 0x00000004
SERVICE_STOPPED = 0x00000001
SERVICE_ACCEPT_STOP = 0x00000001
SERVICE_ACCEPT_SHUTDOWN = 0x00000004
SERVICE_CONTROL_STOP = 0x00000001
SERVICE_CONTROL_INTERROGATE = 0x00000004
SERVICE_CONTROL_SHUTDOWN = 0x00000005
SC_MANAGER_CONNECT = 0x00000001
SC_MANAGER_CREATE_SERVICE = 0x00000002
SERVICE_QUERY_STATUS = 0x00000004
SERVICE_CHANGE_CONFIG = 0x00000002
SERVICE_START = 0x00000010
SERVICE_STOP = 0x00000020
DELETE = 0x00010000
SERVICE_AUTO_START = 0x00000002
SERVICE_ERROR_NORMAL = 0x00000001
SERVICE_CONFIG_DESCRIPTION = 1
SERVICE_CONFIG_FAILURE_ACTIONS = 2
SERVICE_CONFIG_FAILURE_ACTIONS_FLAG = 4
SC_ACTION_RESTART = 1
ERROR_SERVICE_ALREADY_RUNNING = 1056
ERROR_SERVICE_DOES_NOT_EXIST = 1060
ERROR_SERVICE_NOT_ACTIVE = 1062
ERROR_SERVICE_MARKED_FOR_DELETE = 1072
NO_ERROR = 0
ERROR_CALL_NOT_IMPLEMENTED = 120
WAIT_OBJECT_0 = 0
WAIT_TIMEOUT = 258
STILL_ACTIVE = 259
WTS_ACTIVE = 0
TH32CS_SNAPPROCESS = 0x00000002
PROCESS_SYNCHRONIZE = 0x00100000
PROCESS_QUERY_LIMITED_INFORMATION = 0x00001000
CREATE_UNICODE_ENVIRONMENT = 0x00000400
CREATE_NEW_PROCESS_GROUP = 0x00000200
TOKEN_ADJUST_PRIVILEGES = 0x00000020
TOKEN_QUERY = 0x00000008
SE_PRIVILEGE_ENABLED = 0x00000002

WINFUNCTYPE = getattr(ctypes, "WINFUNCTYPE", ctypes.CFUNCTYPE)
ULONG_PTR = ctypes.c_size_t


class SERVICE_STATUS(ctypes.Structure):
    _fields_ = [
        ("dwServiceType", wintypes.DWORD),
        ("dwCurrentState", wintypes.DWORD),
        ("dwControlsAccepted", wintypes.DWORD),
        ("dwWin32ExitCode", wintypes.DWORD),
        ("dwServiceSpecificExitCode", wintypes.DWORD),
        ("dwCheckPoint", wintypes.DWORD),
        ("dwWaitHint", wintypes.DWORD),
    ]


class SERVICE_DESCRIPTIONW(ctypes.Structure):
    _fields_ = [("lpDescription", wintypes.LPWSTR)]


class SC_ACTION(ctypes.Structure):
    _fields_ = [("Type", wintypes.DWORD), ("Delay", wintypes.DWORD)]


class SERVICE_FAILURE_ACTIONSW(ctypes.Structure):
    _fields_ = [
        ("dwResetPeriod", wintypes.DWORD),
        ("lpRebootMsg", wintypes.LPWSTR),
        ("lpCommand", wintypes.LPWSTR),
        ("cActions", wintypes.DWORD),
        ("lpsaActions", ctypes.POINTER(SC_ACTION)),
    ]


class SERVICE_FAILURE_ACTIONS_FLAG(ctypes.Structure):
    _fields_ = [("fFailureActionsOnNonCrashFailures", wintypes.BOOL)]


class SHELLEXECUTEINFOW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("fMask", wintypes.ULONG),
        ("hwnd", wintypes.HWND),
        ("lpVerb", wintypes.LPCWSTR),
        ("lpFile", wintypes.LPCWSTR),
        ("lpParameters", wintypes.LPCWSTR),
        ("lpDirectory", wintypes.LPCWSTR),
        ("nShow", ctypes.c_int),
        ("hInstApp", wintypes.HINSTANCE),
        ("lpIDList", wintypes.LPVOID),
        ("lpClass", wintypes.LPCWSTR),
        ("hkeyClass", wintypes.HKEY),
        ("dwHotKey", wintypes.DWORD),
        ("hIconOrMonitor", wintypes.HANDLE),
        ("hProcess", wintypes.HANDLE),
    ]


class STARTUPINFOW(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("lpReserved", wintypes.LPWSTR),
        ("lpDesktop", wintypes.LPWSTR),
        ("lpTitle", wintypes.LPWSTR),
        ("dwX", wintypes.DWORD),
        ("dwY", wintypes.DWORD),
        ("dwXSize", wintypes.DWORD),
        ("dwYSize", wintypes.DWORD),
        ("dwXCountChars", wintypes.DWORD),
        ("dwYCountChars", wintypes.DWORD),
        ("dwFillAttribute", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("wShowWindow", wintypes.WORD),
        ("cbReserved2", wintypes.WORD),
        ("lpReserved2", ctypes.POINTER(ctypes.c_byte)),
        ("hStdInput", wintypes.HANDLE),
        ("hStdOutput", wintypes.HANDLE),
        ("hStdError", wintypes.HANDLE),
    ]


class PROCESS_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("hProcess", wintypes.HANDLE),
        ("hThread", wintypes.HANDLE),
        ("dwProcessId", wintypes.DWORD),
        ("dwThreadId", wintypes.DWORD),
    ]


class WTS_SESSION_INFOW(ctypes.Structure):
    _fields_ = [
        ("SessionId", wintypes.DWORD),
        ("pWinStationName", wintypes.LPWSTR),
        ("State", wintypes.DWORD),
    ]


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ULONG_PTR),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", wintypes.LONG),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", wintypes.WCHAR * 260),
    ]


class LUID(ctypes.Structure):
    _fields_ = [("LowPart", wintypes.DWORD), ("HighPart", wintypes.LONG)]


class LUID_AND_ATTRIBUTES(ctypes.Structure):
    _fields_ = [("Luid", LUID), ("Attributes", wintypes.DWORD)]


class TOKEN_PRIVILEGES(ctypes.Structure):
    _fields_ = [
        ("PrivilegeCount", wintypes.DWORD),
        ("Privileges", LUID_AND_ATTRIBUTES * 1),
    ]


SERVICE_MAIN_FUNCTION = WINFUNCTYPE(None, wintypes.DWORD, ctypes.POINTER(wintypes.LPWSTR))
HANDLER_FUNCTION_EX = WINFUNCTYPE(
    wintypes.DWORD,
    wintypes.DWORD,
    wintypes.DWORD,
    wintypes.LPVOID,
    wintypes.LPVOID,
)


class SERVICE_TABLE_ENTRYW(ctypes.Structure):
    _fields_ = [
        ("lpServiceName", wintypes.LPWSTR),
        ("lpServiceProc", SERVICE_MAIN_FUNCTION),
    ]


@dataclass
class _ChildProcess:
    process_handle: wintypes.HANDLE
    process_id: int
    started_at: float


class WindowsWatchdogManager:
    """Install, configure, and remove the SCM-managed watchdog service."""

    SERVICE_NAME = "BlinkCallWatchdog"
    SERVICE_DISPLAY_NAME = "BlinkCall Watchdog"
    SERVICE_DESCRIPTION = "Keeps BlinkCall running in active user sessions."
    RECOVERY_RESET_SECONDS = 24 * 60 * 60
    LEGACY_TASK_NAME = "BlinkCall - AutoStart"
    STATUS_TIMEOUT_SECONDS = 30

    @classmethod
    def is_supported(cls) -> bool:
        return sys.platform == "win32"

    @classmethod
    def set_enabled(cls, enabled: bool) -> tuple[bool, str]:
        if not cls.is_supported():
            return False, "The BlinkCall watchdog is available only on Windows."
        elevated = cls._is_elevated()
        logger.info("watchdog_configuration_requested enabled=%s elevated=%s pid=%s", enabled, elevated, os.getpid())
        if not elevated:
            return cls._configure_with_elevation(enabled)
        return cls._set_enabled_elevated(enabled)

    @classmethod
    def _set_enabled_elevated(cls, enabled: bool) -> tuple[bool, str]:
        if not cls._is_elevated():
            return False, "Windows did not grant administrator privileges to the watchdog configuration process."
        try:
            return cls._install_and_start() if enabled else cls._stop_and_remove()
        except OSError as exc:
            logger.exception("watchdog_configuration_failed enabled=%s", enabled)
            return False, f"{exc}\n\nService log: {_service_log_path()}"

    @classmethod
    def _configure_with_elevation(cls, enabled: bool) -> tuple[bool, str]:
        executable = cls._packaged_executable()
        if executable is None:
            return False, "The watchdog can be installed only from the packaged BlinkCall.exe build."

        shell32 = ctypes.WinDLL("shell32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        shell32.ShellExecuteExW.argtypes = [ctypes.POINTER(SHELLEXECUTEINFOW)]
        shell32.ShellExecuteExW.restype = wintypes.BOOL
        kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel32.WaitForSingleObject.restype = wintypes.DWORD
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL

        # Use a separate entrypoint before Qt and single-instance activation.
        # An elevated second GUI would otherwise just activate the existing
        # non-elevated window and leave its effective privileges unchanged.
        with tempfile.TemporaryDirectory(prefix="blinkcall-watchdog-") as directory:
            result_path = Path(directory) / "result.json"
            execute_info = SHELLEXECUTEINFOW()
            execute_info.cbSize = ctypes.sizeof(execute_info)
            execute_info.fMask = 0x00000040 | 0x00000100  # NOCLOSEPROCESS | NOASYNC
            execute_info.lpVerb = "runas"
            execute_info.lpFile = str(executable)
            execute_info.lpParameters = subprocess.list2cmdline(
                [WATCHDOG_CONFIGURE_ARGUMENT, "enable" if enabled else "disable", str(result_path)]
            )
            execute_info.lpDirectory = str(executable.parent)
            execute_info.nShow = 0
            with _shell_com_apartment():
                if not shell32.ShellExecuteExW(ctypes.byref(execute_info)):
                    if ctypes.get_last_error() == 1223:  # ERROR_CANCELLED
                        return False, "Administrator authorization was cancelled. The watchdog setting was not changed."
                    raise _win_error("ShellExecuteExW(runas)")
            if not execute_info.hProcess:
                return False, "Windows did not return a handle for the watchdog configuration process."
            try:
                if kernel32.WaitForSingleObject(execute_info.hProcess, 0xFFFFFFFF) != WAIT_OBJECT_0:
                    raise _win_error("WaitForSingleObject(configuration)")
            finally:
                kernel32.CloseHandle(execute_info.hProcess)
            try:
                result = json.loads(result_path.read_text(encoding="utf-8"))
                if isinstance(result, dict) and type(result.get("ok")) is bool and isinstance(result.get("error"), str):
                    return result["ok"], result["error"]
            except (OSError, ValueError):
                logger.warning("watchdog_configuration_result_unavailable", exc_info=True)
            return (
                False,
                "The elevated watchdog configuration process exited without a valid result.\n"
                f"Service log: {_service_log_path()}",
            )

    @classmethod
    def _install_and_start(cls) -> tuple[bool, str]:
        service_command = cls._service_command()
        if service_command is None:
            return (
                False,
                "The watchdog can be installed only from the packaged BlinkCall.exe build.",
            )

        api = _ServiceControlApi()
        access = SERVICE_QUERY_STATUS | SERVICE_CHANGE_CONFIG | SERVICE_START | SERVICE_STOP | DELETE
        with api.manager(create=True) as manager:
            service = api.open_service(manager, cls.SERVICE_NAME, access)
            created = service is None
            if created:
                service = api.advapi32.CreateServiceW(
                    manager,
                    cls.SERVICE_NAME,
                    cls.SERVICE_DISPLAY_NAME,
                    access,
                    SERVICE_WIN32_OWN_PROCESS,
                    SERVICE_AUTO_START,
                    SERVICE_ERROR_NORMAL,
                    service_command,
                    None,
                    None,
                    None,
                    None,
                    None,
                )
                if not service:
                    raise _win_error("CreateServiceW")
            try:
                # Updating binPath alone leaves the old watchdog running. Stop
                # it before changing the command and explicitly restore the
                # LocalSystem account required by WTSQueryUserToken.
                if not created:
                    cls._stop_service(api, service)
                    if not api.advapi32.ChangeServiceConfigW(
                        service,
                        SERVICE_WIN32_OWN_PROCESS,
                        SERVICE_AUTO_START,
                        SERVICE_ERROR_NORMAL,
                        service_command,
                        None,
                        None,
                        None,
                        "LocalSystem",
                        None,
                        cls.SERVICE_DISPLAY_NAME,
                    ):
                        raise _win_error("ChangeServiceConfigW")
                cls._configure_recovery(api, service)
                if not api.advapi32.StartServiceW(service, 0, None):
                    if ctypes.get_last_error() != ERROR_SERVICE_ALREADY_RUNNING:
                        raise _win_error("StartServiceW")
                cls._wait_for_state(api, service, SERVICE_RUNNING)
            except Exception:
                # Do not leave a new auto-start service behind when the UI
                # rolls its checkbox back after a failed installation.
                if created:
                    try:
                        cls._stop_service(api, service)
                    except OSError:
                        logger.warning("watchdog_install_rollback_stop_failed", exc_info=True)
                    if not api.advapi32.DeleteService(service):
                        logger.warning("watchdog_install_rollback_delete_failed error=%s", ctypes.get_last_error())
                raise
            finally:
                api.advapi32.CloseServiceHandle(service)

        cls._cleanup_legacy_task()
        logger.info("watchdog_enabled service=%s", cls.SERVICE_NAME)
        return True, ""

    @classmethod
    def _stop_and_remove(cls) -> tuple[bool, str]:
        api = _ServiceControlApi()
        with api.manager() as manager:
            try:
                service = api.open_service(manager, cls.SERVICE_NAME, SERVICE_QUERY_STATUS | SERVICE_STOP | DELETE)
            except OSError as exc:
                if exc.errno != ERROR_SERVICE_MARKED_FOR_DELETE:
                    raise
                service = None
            if service:
                try:
                    cls._stop_service(api, service)
                    if not api.advapi32.DeleteService(service):
                        if ctypes.get_last_error() != ERROR_SERVICE_MARKED_FOR_DELETE:
                            raise _win_error("DeleteService")
                finally:
                    api.advapi32.CloseServiceHandle(service)

        cls._cleanup_legacy_task()
        logger.info("watchdog_disabled service=%s", cls.SERVICE_NAME)
        return True, ""

    @classmethod
    def _configure_recovery(cls, api, service) -> None:
        actions = (SC_ACTION * 3)(
            SC_ACTION(SC_ACTION_RESTART, 5_000),
            SC_ACTION(SC_ACTION_RESTART, 15_000),
            SC_ACTION(SC_ACTION_RESTART, 60_000),
        )
        recovery = SERVICE_FAILURE_ACTIONSW(cls.RECOVERY_RESET_SECONDS, None, None, len(actions), actions)
        failure_flag = SERVICE_FAILURE_ACTIONS_FLAG(True)
        description = SERVICE_DESCRIPTIONW(cls.SERVICE_DESCRIPTION)
        for level, value in (
            (SERVICE_CONFIG_FAILURE_ACTIONS, recovery),
            (SERVICE_CONFIG_FAILURE_ACTIONS_FLAG, failure_flag),
            (SERVICE_CONFIG_DESCRIPTION, description),
        ):
            if not api.advapi32.ChangeServiceConfig2W(service, level, ctypes.byref(value)):
                raise _win_error(f"ChangeServiceConfig2W({level})")

    @classmethod
    def _stop_service(cls, api, service) -> None:
        status = api.query_status(service)
        if status.dwCurrentState == SERVICE_STOPPED:
            return
        if status.dwCurrentState == SERVICE_START_PENDING:
            cls._wait_for_state(api, service, SERVICE_RUNNING)
            status = api.query_status(service)
        if status.dwCurrentState != SERVICE_STOP_PENDING:
            if not api.advapi32.ControlService(service, SERVICE_CONTROL_STOP, ctypes.byref(status)):
                if ctypes.get_last_error() != ERROR_SERVICE_NOT_ACTIVE:
                    raise _win_error("ControlService(STOP)")
        cls._wait_for_state(api, service, SERVICE_STOPPED)

    @classmethod
    def _wait_for_state(cls, api, service, target: int) -> None:
        deadline = time.monotonic() + cls.STATUS_TIMEOUT_SECONDS
        while True:
            status = api.query_status(service)
            if status.dwCurrentState == target:
                return
            if target == SERVICE_RUNNING and status.dwCurrentState == SERVICE_STOPPED:
                raise OSError(
                    status.dwWin32ExitCode or 1,
                    "BlinkCall watchdog stopped during startup "
                    f"(Win32={status.dwWin32ExitCode}, service={status.dwServiceSpecificExitCode}).",
                )
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    f"Timed out waiting for BlinkCall watchdog state {target}; current={status.dwCurrentState}."
                )
            time.sleep(0.2)

    @classmethod
    def _cleanup_legacy_task(cls) -> None:
        # Legacy task cleanup must not report a working service as failed.
        removed, error = cls._remove_legacy_task()
        if not removed:
            logger.warning("legacy_task_cleanup_failed detail=%s", error)

    @classmethod
    def _service_command(cls) -> str | None:
        # Nuitka may retain the build interpreter in ``sys.executable`` even
        # when the application was launched through the standalone executable.
        # ``sys.argv[0]`` is the actual launcher in that case.  Only accept the
        # expected packaged image name so a source/Python invocation can never
        # register a service pointing at a development interpreter.
        executable = cls._packaged_executable()
        if executable is None:
            return None
        return subprocess.list2cmdline([str(executable), WATCHDOG_SERVICE_ARGUMENT])

    @staticmethod
    def _packaged_executable() -> Path | None:
        """Return the standalone BlinkCall executable, if this is one."""
        executable_candidates = [sys.argv[0] if sys.argv else "", sys.executable]
        for candidate in executable_candidates:
            if not candidate:
                continue
            try:
                executable = Path(candidate).resolve()
            except (OSError, RuntimeError):
                continue
            if executable.name.casefold() == "blinkcall.exe":
                return executable
        return None

    @staticmethod
    def _is_elevated() -> bool:
        try:
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
            kernel32.GetCurrentProcess.argtypes = []
            kernel32.GetCurrentProcess.restype = wintypes.HANDLE
            kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
            kernel32.CloseHandle.restype = wintypes.BOOL
            advapi32.OpenProcessToken.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)]
            advapi32.OpenProcessToken.restype = wintypes.BOOL
            advapi32.GetTokenInformation.argtypes = [
                wintypes.HANDLE,
                ctypes.c_int,
                wintypes.LPVOID,
                wintypes.DWORD,
                ctypes.POINTER(wintypes.DWORD),
            ]
            advapi32.GetTokenInformation.restype = wintypes.BOOL
            token = wintypes.HANDLE()
            if not advapi32.OpenProcessToken(kernel32.GetCurrentProcess(), TOKEN_QUERY, ctypes.byref(token)):
                raise _win_error("OpenProcessToken(elevation)")
            try:
                elevated = wintypes.DWORD()
                size = wintypes.DWORD()
                if not advapi32.GetTokenInformation(
                    token, 20, ctypes.byref(elevated), ctypes.sizeof(elevated), ctypes.byref(size)
                ):  # TokenElevation
                    raise _win_error("GetTokenInformation(TokenElevation)")
                return bool(elevated.value)
            finally:
                kernel32.CloseHandle(token)
        except (AttributeError, OSError):
            logger.warning("watchdog_elevation_query_failed", exc_info=True)
            return False

    @classmethod
    def _remove_legacy_task(cls) -> tuple[bool, str]:
        """Remove the former logon task so it cannot duplicate the GUI."""
        windows_dir = os.environ.get("WINDIR")
        scheduler = Path(windows_dir) / "System32" / "schtasks.exe" if windows_dir else None
        command = str(scheduler) if scheduler and scheduler.is_file() else "schtasks.exe"
        try:
            result = subprocess.run(
                [command, "/Delete", "/TN", cls.LEGACY_TASK_NAME, "/F"],
                capture_output=True,
                text=True,
                encoding=_system_command_encoding(),
                errors="replace",
                check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                timeout=10,
            )
            if result.returncode == 0 or cls._legacy_task_not_found(result):
                return True, ""
            return False, cls._format_command_error(result)
        except (OSError, subprocess.TimeoutExpired):
            logger.warning("legacy_task_remove_failed", exc_info=True)
            return False, "Unable to remove the legacy BlinkCall scheduled task."

    @staticmethod
    def _legacy_task_not_found(result: subprocess.CompletedProcess) -> bool:
        output = f"{result.stdout}\n{result.stderr}".lower()
        return any(marker in output for marker in ("does not exist", "cannot find", "找不到", "不存在"))

    @staticmethod
    def _format_command_error(result: subprocess.CompletedProcess) -> str:
        output = (result.stderr or result.stdout or "").strip()
        return output or f"Windows service command failed with exit code {result.returncode}."


class _ServiceControlApi:
    """SCM bindings; service errors are numeric and independent of locale."""

    def __init__(self):
        self.advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
        signatures = {
            "OpenSCManagerW": ([wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD], wintypes.HANDLE),
            "OpenServiceW": ([wintypes.HANDLE, wintypes.LPCWSTR, wintypes.DWORD], wintypes.HANDLE),
            "CreateServiceW": (
                [
                    wintypes.HANDLE,
                    wintypes.LPCWSTR,
                    wintypes.LPCWSTR,
                    wintypes.DWORD,
                    wintypes.DWORD,
                    wintypes.DWORD,
                    wintypes.DWORD,
                    wintypes.LPCWSTR,
                    wintypes.LPCWSTR,
                    ctypes.POINTER(wintypes.DWORD),
                    wintypes.LPCWSTR,
                    wintypes.LPCWSTR,
                    wintypes.LPCWSTR,
                ],
                wintypes.HANDLE,
            ),
            "ChangeServiceConfigW": (
                [
                    wintypes.HANDLE,
                    wintypes.DWORD,
                    wintypes.DWORD,
                    wintypes.DWORD,
                    wintypes.LPCWSTR,
                    wintypes.LPCWSTR,
                    ctypes.POINTER(wintypes.DWORD),
                    wintypes.LPCWSTR,
                    wintypes.LPCWSTR,
                    wintypes.LPCWSTR,
                    wintypes.LPCWSTR,
                ],
                wintypes.BOOL,
            ),
            "ChangeServiceConfig2W": ([wintypes.HANDLE, wintypes.DWORD, wintypes.LPVOID], wintypes.BOOL),
            "StartServiceW": ([wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.LPCWSTR)], wintypes.BOOL),
            "ControlService": ([wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(SERVICE_STATUS)], wintypes.BOOL),
            "QueryServiceStatus": ([wintypes.HANDLE, ctypes.POINTER(SERVICE_STATUS)], wintypes.BOOL),
            "DeleteService": ([wintypes.HANDLE], wintypes.BOOL),
            "CloseServiceHandle": ([wintypes.HANDLE], wintypes.BOOL),
        }
        for name, (arguments, result) in signatures.items():
            function = getattr(self.advapi32, name)
            function.argtypes = arguments
            function.restype = result

    @contextmanager
    def manager(self, create=False):
        access = SC_MANAGER_CONNECT | (SC_MANAGER_CREATE_SERVICE if create else 0)
        handle = self.advapi32.OpenSCManagerW(None, None, access)
        if not handle:
            raise _win_error("OpenSCManagerW")
        try:
            yield handle
        finally:
            self.advapi32.CloseServiceHandle(handle)

    def open_service(self, manager, name, access):
        service = self.advapi32.OpenServiceW(manager, name, access)
        if not service:
            if ctypes.get_last_error() == ERROR_SERVICE_DOES_NOT_EXIST:
                return None
            raise _win_error("OpenServiceW")
        return service

    def query_status(self, service) -> SERVICE_STATUS:
        status = SERVICE_STATUS()
        if not self.advapi32.QueryServiceStatus(service, ctypes.byref(status)):
            raise _win_error("QueryServiceStatus")
        return status


class WindowsWatchdogService:
    """SCM entrypoint and per-session BlinkCall process supervisor."""

    POLL_INTERVAL_MS = 2_000
    STABLE_RUNTIME_SECONDS = 5 * 60
    MAX_RESTART_DELAY_SECONDS = 5 * 60

    def __init__(self):
        self._api: _WindowsApi | None = None
        self._status_handle = None
        self._status = SERVICE_STATUS()
        self._stop_event = None
        self._children: dict[int, _ChildProcess] = {}
        self._failure_counts: dict[int, int] = {}
        self._retry_after: dict[int, float] = {}
        self._suppressed_sessions: set[int] = set()
        self._service_main_callback = None
        self._control_callback = None
        self._logger = _configure_service_logging()

        # In a Nuitka standalone build ``sys.executable`` can still point to
        # the Python interpreter used to create the build.  A service started
        # from BlinkCall.exe must relaunch that executable in the interactive
        # session, not that interpreter without an application script.
        executable = WindowsWatchdogManager._packaged_executable()
        if executable is None:
            executable = Path(sys.argv[0] if sys.argv else sys.executable).resolve()
        self._app_command = [
            str(executable),
            WATCHDOG_SUPERVISED_ARGUMENT,
        ]
        self._app_working_directory = executable.parent
        self._app_image_name = executable.name.casefold()

    def run(self) -> int:
        if sys.platform != "win32":
            return 1
        self._api = _WindowsApi()
        self._service_main_callback = SERVICE_MAIN_FUNCTION(self._service_main)
        table = (SERVICE_TABLE_ENTRYW * 2)()
        table[0].lpServiceName = WindowsWatchdogManager.SERVICE_NAME
        table[0].lpServiceProc = self._service_main_callback
        if self._api.advapi32.StartServiceCtrlDispatcherW(table):
            return 0
        return ctypes.get_last_error() or 1

    def _service_main(self, _argument_count, _arguments) -> None:
        assert self._api is not None
        self._control_callback = HANDLER_FUNCTION_EX(self._service_control_handler)
        self._status_handle = self._api.advapi32.RegisterServiceCtrlHandlerExW(
            WindowsWatchdogManager.SERVICE_NAME,
            self._control_callback,
            None,
        )
        if not self._status_handle:
            return

        self._report_status(SERVICE_START_PENDING, wait_hint=10_000)
        self._stop_event = self._api.kernel32.CreateEventW(None, True, False, None)
        if not self._stop_event:
            self._report_status(SERVICE_STOPPED, win32_exit=ctypes.get_last_error() or 1)
            return

        try:
            self._enable_required_privileges()
            self._report_status(SERVICE_RUNNING)
            self._logger.info("watchdog_service_started")
            self._supervise()
            self._report_status(SERVICE_STOPPED)
        except Exception:
            self._logger.exception("watchdog_service_failed")
            self._report_status(SERVICE_STOPPED, win32_exit=1)
        finally:
            if self._stop_event:
                self._api.kernel32.CloseHandle(self._stop_event)
                self._stop_event = None
            self._close_child_handles()

    def _service_control_handler(self, control, _event_type, _event_data, _context) -> int:
        if control in (SERVICE_CONTROL_STOP, SERVICE_CONTROL_SHUTDOWN):
            self._report_status(SERVICE_STOP_PENDING, wait_hint=10_000)
            if self._stop_event:
                assert self._api is not None
                self._api.kernel32.SetEvent(self._stop_event)
            return NO_ERROR
        if control == SERVICE_CONTROL_INTERROGATE:
            self._report_status(self._status.dwCurrentState)
            return NO_ERROR
        return ERROR_CALL_NOT_IMPLEMENTED

    def _report_status(self, state: int, win32_exit: int = 0, wait_hint: int = 0) -> None:
        if not self._status_handle or self._api is None:
            return
        self._status.dwServiceType = SERVICE_WIN32_OWN_PROCESS
        self._status.dwCurrentState = state
        self._status.dwControlsAccepted = (
            SERVICE_ACCEPT_STOP | SERVICE_ACCEPT_SHUTDOWN if state == SERVICE_RUNNING else 0
        )
        self._status.dwWin32ExitCode = win32_exit
        self._status.dwServiceSpecificExitCode = 0
        self._status.dwCheckPoint = 1 if state in (SERVICE_START_PENDING, SERVICE_STOP_PENDING) else 0
        self._status.dwWaitHint = wait_hint
        self._api.advapi32.SetServiceStatus(self._status_handle, ctypes.byref(self._status))

    def _supervise(self) -> None:
        assert self._api is not None
        while True:
            wait_result = self._api.kernel32.WaitForSingleObject(self._stop_event, self.POLL_INTERVAL_MS)
            if wait_result == WAIT_OBJECT_0:
                return
            if wait_result != WAIT_TIMEOUT:
                raise _win_error("WaitForSingleObject")
            active_session_ids = set(self._active_sessions())
            self._remove_inactive_sessions(active_session_ids)
            self._poll_children(active_session_ids)
            self._ensure_children(active_session_ids)

    def _active_sessions(self) -> list[int]:
        assert self._api is not None
        sessions = ctypes.POINTER(WTS_SESSION_INFOW)()
        count = wintypes.DWORD()
        if not self._api.wtsapi32.WTSEnumerateSessionsW(
            None, 0, 1, ctypes.byref(sessions), ctypes.byref(count)
        ):
            self._logger.warning("watchdog_sessions_enumeration_failed error=%s", ctypes.get_last_error())
            return []

        try:
            return [
                sessions[index].SessionId
                for index in range(count.value)
                if sessions[index].State == WTS_ACTIVE
            ]
        finally:
            self._api.wtsapi32.WTSFreeMemory(sessions)

    def _remove_inactive_sessions(self, active_session_ids: set[int]) -> None:
        assert self._api is not None
        for session_id in list(self._children):
            if session_id not in active_session_ids:
                self._api.kernel32.CloseHandle(self._children.pop(session_id).process_handle)
        self._suppressed_sessions.intersection_update(active_session_ids)
        self._retry_after = {
            session_id: retry_at
            for session_id, retry_at in self._retry_after.items()
            if session_id in active_session_ids
        }
        self._failure_counts = {
            session_id: failure_count
            for session_id, failure_count in self._failure_counts.items()
            if session_id in active_session_ids
        }

    def _poll_children(self, active_session_ids: set[int]) -> None:
        assert self._api is not None
        for session_id, child in list(self._children.items()):
            if session_id not in active_session_ids:
                continue
            if self._api.kernel32.WaitForSingleObject(child.process_handle, 0) != WAIT_OBJECT_0:
                if time.monotonic() - child.started_at >= self.STABLE_RUNTIME_SECONDS:
                    self._failure_counts.pop(session_id, None)
                continue

            exit_code = wintypes.DWORD()
            self._api.kernel32.GetExitCodeProcess(child.process_handle, ctypes.byref(exit_code))
            self._api.kernel32.CloseHandle(child.process_handle)
            del self._children[session_id]

            if exit_code.value == WATCHDOG_USER_EXIT_CODE:
                self._suppressed_sessions.add(session_id)
                self._retry_after.pop(session_id, None)
                self._failure_counts.pop(session_id, None)
                self._logger.info("app_exit_requested session=%s pid=%s", session_id, child.process_id)
                continue

            failure_count = self._failure_counts.get(session_id, 0) + 1
            self._failure_counts[session_id] = failure_count
            delay = min(5 * (2 ** (failure_count - 1)), self.MAX_RESTART_DELAY_SECONDS)
            self._retry_after[session_id] = time.monotonic() + delay
            self._logger.warning(
                "app_exit_unexpected session=%s pid=%s exit_code=%s retry_delay_s=%s",
                session_id,
                child.process_id,
                exit_code.value,
                delay,
            )

    def _ensure_children(self, active_session_ids: set[int]) -> None:
        now = time.monotonic()
        for session_id in active_session_ids:
            if session_id in self._children or session_id in self._suppressed_sessions:
                continue
            if now < self._retry_after.get(session_id, 0):
                continue

            existing_child = self._find_existing_app(session_id)
            if existing_child is not None:
                self._children[session_id] = existing_child
                self._logger.info("app_watch_adopted session=%s pid=%s", session_id, existing_child.process_id)
                continue

            try:
                self._children[session_id] = self._start_app_for_session(session_id)
                self._retry_after.pop(session_id, None)
            except OSError as exc:
                self._retry_after[session_id] = now + 30
                self._logger.warning("app_start_failed session=%s detail=%s", session_id, exc)

    def _find_existing_app(self, session_id: int) -> _ChildProcess | None:
        assert self._api is not None
        snapshot = self._api.kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
        invalid_handle = ctypes.c_void_p(-1).value
        if snapshot == invalid_handle:
            return None

        try:
            entry = PROCESSENTRY32W()
            entry.dwSize = ctypes.sizeof(entry)
            if not self._api.kernel32.Process32FirstW(snapshot, ctypes.byref(entry)):
                return None
            while True:
                if entry.szExeFile.casefold() == self._app_image_name:
                    process_session_id = wintypes.DWORD()
                    if self._api.kernel32.ProcessIdToSessionId(
                        entry.th32ProcessID, ctypes.byref(process_session_id)
                    ) and process_session_id.value == session_id:
                        process_handle = self._api.kernel32.OpenProcess(
                            PROCESS_SYNCHRONIZE | PROCESS_QUERY_LIMITED_INFORMATION,
                            False,
                            entry.th32ProcessID,
                        )
                        if process_handle:
                            return _ChildProcess(process_handle, entry.th32ProcessID, time.monotonic())
                if not self._api.kernel32.Process32NextW(snapshot, ctypes.byref(entry)):
                    return None
        finally:
            self._api.kernel32.CloseHandle(snapshot)

    def _start_app_for_session(self, session_id: int) -> _ChildProcess:
        assert self._api is not None
        user_token = wintypes.HANDLE()
        if not self._api.wtsapi32.WTSQueryUserToken(session_id, ctypes.byref(user_token)):
            raise _win_error("WTSQueryUserToken")

        environment = wintypes.LPVOID()
        process_info = PROCESS_INFORMATION()
        try:
            if not self._api.userenv.CreateEnvironmentBlock(
                ctypes.byref(environment), user_token, False
            ):
                raise _win_error("CreateEnvironmentBlock")

            startup_info = STARTUPINFOW()
            startup_info.cb = ctypes.sizeof(startup_info)
            startup_info.lpDesktop = "winsta0\\default"
            command_line = ctypes.create_unicode_buffer(subprocess.list2cmdline(self._app_command))
            if not self._api.advapi32.CreateProcessAsUserW(
                user_token,
                None,
                command_line,
                None,
                None,
                False,
                CREATE_UNICODE_ENVIRONMENT | CREATE_NEW_PROCESS_GROUP,
                environment,
                str(self._app_working_directory),
                ctypes.byref(startup_info),
                ctypes.byref(process_info),
            ):
                raise _win_error("CreateProcessAsUser")
            self._api.kernel32.CloseHandle(process_info.hThread)
            self._logger.info("app_started session=%s pid=%s", session_id, process_info.dwProcessId)
            return _ChildProcess(process_info.hProcess, process_info.dwProcessId, time.monotonic())
        finally:
            if environment:
                self._api.userenv.DestroyEnvironmentBlock(environment)
            self._api.kernel32.CloseHandle(user_token)

    def _enable_required_privileges(self) -> None:
        self._enable_privilege("SeTcbPrivilege")
        self._enable_privilege("SeAssignPrimaryTokenPrivilege")
        self._enable_privilege("SeIncreaseQuotaPrivilege")

    def _enable_privilege(self, privilege_name: str) -> None:
        assert self._api is not None
        token = wintypes.HANDLE()
        if not self._api.advapi32.OpenProcessToken(
            self._api.kernel32.GetCurrentProcess(),
            TOKEN_ADJUST_PRIVILEGES | TOKEN_QUERY,
            ctypes.byref(token),
        ):
            raise _win_error(f"OpenProcessToken({privilege_name})")

        try:
            luid = LUID()
            if not self._api.advapi32.LookupPrivilegeValueW(None, privilege_name, ctypes.byref(luid)):
                raise _win_error(f"LookupPrivilegeValue({privilege_name})")
            privileges = TOKEN_PRIVILEGES()
            privileges.PrivilegeCount = 1
            privileges.Privileges[0] = LUID_AND_ATTRIBUTES(luid, SE_PRIVILEGE_ENABLED)
            ctypes.set_last_error(0)
            self._api.advapi32.AdjustTokenPrivileges(
                token, False, ctypes.byref(privileges), 0, None, None
            )
            if ctypes.get_last_error():
                raise _win_error(f"AdjustTokenPrivileges({privilege_name})")
        finally:
            self._api.kernel32.CloseHandle(token)

    def _close_child_handles(self) -> None:
        if self._api is None:
            return
        for child in self._children.values():
            self._api.kernel32.CloseHandle(child.process_handle)
        self._children.clear()


class _WindowsApi:
    """Typed Win32 DLL bindings used only in the watchdog service process."""

    def __init__(self):
        self.advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
        self.kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self.userenv = ctypes.WinDLL("userenv", use_last_error=True)
        self.wtsapi32 = ctypes.WinDLL("wtsapi32", use_last_error=True)
        self._bind_functions()

    def _bind_functions(self) -> None:
        self.advapi32.StartServiceCtrlDispatcherW.argtypes = [ctypes.POINTER(SERVICE_TABLE_ENTRYW)]
        self.advapi32.StartServiceCtrlDispatcherW.restype = wintypes.BOOL
        self.advapi32.RegisterServiceCtrlHandlerExW.argtypes = [
            wintypes.LPCWSTR,
            HANDLER_FUNCTION_EX,
            wintypes.LPVOID,
        ]
        self.advapi32.RegisterServiceCtrlHandlerExW.restype = wintypes.HANDLE
        self.advapi32.SetServiceStatus.argtypes = [wintypes.HANDLE, ctypes.POINTER(SERVICE_STATUS)]
        self.advapi32.SetServiceStatus.restype = wintypes.BOOL
        self.advapi32.CreateProcessAsUserW.argtypes = [
            wintypes.HANDLE,
            wintypes.LPCWSTR,
            wintypes.LPWSTR,
            wintypes.LPVOID,
            wintypes.LPVOID,
            wintypes.BOOL,
            wintypes.DWORD,
            wintypes.LPVOID,
            wintypes.LPCWSTR,
            ctypes.POINTER(STARTUPINFOW),
            ctypes.POINTER(PROCESS_INFORMATION),
        ]
        self.advapi32.CreateProcessAsUserW.restype = wintypes.BOOL
        self.advapi32.OpenProcessToken.argtypes = [
            wintypes.HANDLE,
            wintypes.DWORD,
            ctypes.POINTER(wintypes.HANDLE),
        ]
        self.advapi32.OpenProcessToken.restype = wintypes.BOOL
        self.advapi32.LookupPrivilegeValueW.argtypes = [
            wintypes.LPCWSTR,
            wintypes.LPCWSTR,
            ctypes.POINTER(LUID),
        ]
        self.advapi32.LookupPrivilegeValueW.restype = wintypes.BOOL
        self.advapi32.AdjustTokenPrivileges.argtypes = [
            wintypes.HANDLE,
            wintypes.BOOL,
            ctypes.POINTER(TOKEN_PRIVILEGES),
            wintypes.DWORD,
            wintypes.LPVOID,
            wintypes.LPVOID,
        ]
        self.advapi32.AdjustTokenPrivileges.restype = wintypes.BOOL

        self.kernel32.CreateEventW.argtypes = [
            wintypes.LPVOID,
            wintypes.BOOL,
            wintypes.BOOL,
            wintypes.LPCWSTR,
        ]
        self.kernel32.CreateEventW.restype = wintypes.HANDLE
        self.kernel32.SetEvent.argtypes = [wintypes.HANDLE]
        self.kernel32.SetEvent.restype = wintypes.BOOL
        self.kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        self.kernel32.WaitForSingleObject.restype = wintypes.DWORD
        self.kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        self.kernel32.CloseHandle.restype = wintypes.BOOL
        self.kernel32.GetExitCodeProcess.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(wintypes.DWORD),
        ]
        self.kernel32.GetExitCodeProcess.restype = wintypes.BOOL
        self.kernel32.GetCurrentProcess.argtypes = []
        self.kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        self.kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
        self.kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
        self.kernel32.Process32FirstW.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(PROCESSENTRY32W),
        ]
        self.kernel32.Process32FirstW.restype = wintypes.BOOL
        self.kernel32.Process32NextW.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(PROCESSENTRY32W),
        ]
        self.kernel32.Process32NextW.restype = wintypes.BOOL
        self.kernel32.ProcessIdToSessionId.argtypes = [
            wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD),
        ]
        self.kernel32.ProcessIdToSessionId.restype = wintypes.BOOL
        self.kernel32.OpenProcess.argtypes = [
            wintypes.DWORD,
            wintypes.BOOL,
            wintypes.DWORD,
        ]
        self.kernel32.OpenProcess.restype = wintypes.HANDLE

        self.userenv.CreateEnvironmentBlock.argtypes = [
            ctypes.POINTER(wintypes.LPVOID),
            wintypes.HANDLE,
            wintypes.BOOL,
        ]
        self.userenv.CreateEnvironmentBlock.restype = wintypes.BOOL
        self.userenv.DestroyEnvironmentBlock.argtypes = [wintypes.LPVOID]
        self.userenv.DestroyEnvironmentBlock.restype = wintypes.BOOL

        self.wtsapi32.WTSEnumerateSessionsW.argtypes = [
            wintypes.HANDLE,
            wintypes.DWORD,
            wintypes.DWORD,
            ctypes.POINTER(ctypes.POINTER(WTS_SESSION_INFOW)),
            ctypes.POINTER(wintypes.DWORD),
        ]
        self.wtsapi32.WTSEnumerateSessionsW.restype = wintypes.BOOL
        self.wtsapi32.WTSQueryUserToken.argtypes = [
            wintypes.DWORD,
            ctypes.POINTER(wintypes.HANDLE),
        ]
        self.wtsapi32.WTSQueryUserToken.restype = wintypes.BOOL
        self.wtsapi32.WTSFreeMemory.argtypes = [wintypes.LPVOID]
        self.wtsapi32.WTSFreeMemory.restype = None


def _configure_service_logging() -> logging.Logger:
    service_logger = logging.getLogger("blink_call.watchdog.service")
    service_logger.setLevel(logging.INFO)
    service_logger.propagate = False
    if service_logger.handlers:
        return service_logger

    log_path = _service_log_path()
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(log_path, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8")
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)s %(name)s [%(threadName)s] %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        service_logger.addHandler(handler)
    except OSError:
        service_logger.addHandler(logging.NullHandler())
    return service_logger


def _service_log_path() -> Path:
    return Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / "BlinkCall" / "logs" / "watchdog.log"


@contextmanager
def _shell_com_apartment():
    # Service configuration runs in a Python worker thread, where Qt has not
    # initialized COM. ShellExecuteEx may invoke COM-based shell extensions.
    ole32 = ctypes.WinDLL("ole32", use_last_error=True)
    ole32.CoInitializeEx.argtypes = [wintypes.LPVOID, wintypes.DWORD]
    ole32.CoInitializeEx.restype = wintypes.LONG
    ole32.CoUninitialize.argtypes = []
    ole32.CoUninitialize.restype = None
    result = ole32.CoInitializeEx(None, 0x2 | 0x4)  # STA | DISABLE_OLE1DDE
    if result < 0 and result != -2147417850:  # RPC_E_CHANGED_MODE: COM already initialized
        raise OSError(f"CoInitializeEx failed (HRESULT=0x{result & 0xFFFFFFFF:08X}).")
    try:
        yield
    finally:
        if result >= 0:
            ole32.CoUninitialize()


def _system_command_encoding() -> str:
    """Decode Windows built-in command output using the local code page."""
    if sys.platform == "win32":
        return locale.getpreferredencoding(False)
    return "utf-8"


def _win_error(operation: str) -> OSError:
    error_code = ctypes.get_last_error() or 1
    return OSError(error_code, f"{operation}: {ctypes.WinError(error_code)}")


def run_watchdog_service() -> int:
    """Run the SCM service entrypoint from ``BlinkCall.exe --watchdog-service``."""
    try:
        return WindowsWatchdogService().run()
    except Exception:
        _configure_service_logging().exception("watchdog_service_entrypoint_failed")
        return 1


def run_watchdog_configuration(arguments: list[str]) -> int:
    """Configure the service in a UAC helper without starting Qt or the GUI."""
    if sys.platform != "win32" or len(arguments) != 2 or arguments[0] not in ("enable", "disable"):
        return 2
    service_logger = _configure_service_logging()
    try:
        ok, error = WindowsWatchdogManager._set_enabled_elevated(arguments[0] == "enable")
    except Exception as exc:
        service_logger.exception("watchdog_configuration_helper_failed")
        ok, error = False, str(exc)
    if not ok:
        service_logger.error("watchdog_configuration_rejected detail=%s", error)
    try:
        Path(arguments[1]).write_text(json.dumps({"ok": ok, "error": error}), encoding="utf-8")
    except OSError:
        service_logger.exception("watchdog_configuration_result_write_failed")
        return 1
    return 0 if ok else 1
