"""Windows service watchdog for keeping BlinkCall available in user sessions.

The GUI application is deliberately not a Windows service: Windows services run
in Session 0 and cannot own a user's tray icon or windows. Instead, this module
installs a small service from the same executable. The service starts the GUI
in each active user session and restarts it after an unexpected exit. The
Service Control Manager (SCM) separately restarts the watchdog itself.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import subprocess
import sys
import time


logger = logging.getLogger("blink_call.watchdog")

WATCHDOG_SERVICE_ARGUMENT = "--watchdog-service"
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

    @classmethod
    def is_supported(cls) -> bool:
        return sys.platform == "win32"

    @classmethod
    def set_enabled(cls, enabled: bool) -> tuple[bool, str]:
        if not cls.is_supported():
            return False, "The BlinkCall watchdog is available only on Windows."
        if not cls._is_elevated():
            return False, "Administrator privileges are required to configure the BlinkCall watchdog."
        return cls._install_and_start() if enabled else cls._stop_and_remove()

    @classmethod
    def _install_and_start(cls) -> tuple[bool, str]:
        service_command = cls._service_command()
        if service_command is None:
            return (
                False,
                "The watchdog can be installed only from the packaged BlinkCall.exe build.",
            )

        sc = cls._sc_executable()
        if sc is None:
            return False, "sc.exe was not found."

        existing = cls._run_sc(sc, "query", cls.SERVICE_NAME)
        if existing.returncode == 0:
            result = cls._run_sc(
                sc,
                "config",
                cls.SERVICE_NAME,
                "binPath=",
                service_command,
                "start=",
                "auto",
            )
        else:
            result = cls._run_sc(
                sc,
                "create",
                cls.SERVICE_NAME,
                "binPath=",
                service_command,
                "start=",
                "auto",
                "DisplayName=",
                cls.SERVICE_DISPLAY_NAME,
            )
        if result.returncode != 0:
            return False, cls._format_command_error(result)

        for args in (
            (
                "failure",
                cls.SERVICE_NAME,
                "reset=",
                str(cls.RECOVERY_RESET_SECONDS),
                "actions=",
                "restart/5000/restart/15000/restart/60000",
            ),
            ("failureflag", cls.SERVICE_NAME, "1"),
            ("description", cls.SERVICE_NAME, cls.SERVICE_DESCRIPTION),
        ):
            result = cls._run_sc(sc, *args)
            if result.returncode != 0:
                return False, cls._format_command_error(result)

        legacy_task_removed, error = cls._remove_legacy_task()
        if not legacy_task_removed:
            return False, error

        result = cls._run_sc(sc, "start", cls.SERVICE_NAME)
        if result.returncode != 0 and not cls._service_already_running(result):
            return False, cls._format_command_error(result)

        logger.info("watchdog_enabled service=%s", cls.SERVICE_NAME)
        return True, ""

    @classmethod
    def _stop_and_remove(cls) -> tuple[bool, str]:
        sc = cls._sc_executable()
        if sc is None:
            return False, "sc.exe was not found."

        result = cls._run_sc(sc, "stop", cls.SERVICE_NAME)
        if result.returncode != 0 and not cls._service_not_running_or_missing(result):
            return False, cls._format_command_error(result)

        result = cls._run_sc(sc, "delete", cls.SERVICE_NAME)
        if result.returncode != 0 and not cls._service_not_running_or_missing(result):
            return False, cls._format_command_error(result)

        legacy_task_removed, error = cls._remove_legacy_task()
        if not legacy_task_removed:
            return False, error

        logger.info("watchdog_disabled service=%s", cls.SERVICE_NAME)
        return True, ""

    @classmethod
    def _service_command(cls) -> str | None:
        # Nuitka may retain the build interpreter in ``sys.executable`` even
        # when the application was launched through the standalone executable.
        # ``sys.argv[0]`` is the actual launcher in that case.  Only accept the
        # expected packaged image name so a source/Python invocation can never
        # register a service pointing at a development interpreter.
        executable_candidates = [sys.argv[0] if sys.argv else "", sys.executable]
        for candidate in executable_candidates:
            if not candidate:
                continue
            try:
                executable = Path(candidate).resolve()
            except (OSError, RuntimeError):
                continue
            if executable.name.casefold() == "blinkcall.exe":
                return subprocess.list2cmdline([str(executable), WATCHDOG_SERVICE_ARGUMENT])
        return None

    @staticmethod
    def _is_elevated() -> bool:
        try:
            shell32 = ctypes.WinDLL("shell32", use_last_error=True)
            return bool(shell32.IsUserAnAdmin())
        except (AttributeError, OSError):
            return False

    @staticmethod
    def _sc_executable() -> str | None:
        windows_dir = os.environ.get("WINDIR")
        candidates = []
        if windows_dir:
            candidates.append(Path(windows_dir) / "System32" / "sc.exe")
        candidates.append(Path("sc.exe"))
        for candidate in candidates:
            if candidate.is_file() or not candidate.is_absolute():
                return str(candidate)
        return None

    @staticmethod
    def _run_sc(sc: str, *arguments: str) -> subprocess.CompletedProcess:
        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        return subprocess.run(
            [sc, *arguments],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            creationflags=creation_flags,
        )

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
                encoding="utf-8",
                errors="replace",
                check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if result.returncode == 0 or cls._legacy_task_not_found(result):
                return True, ""
            return False, cls._format_command_error(result)
        except OSError:
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

    @staticmethod
    def _service_already_running(result: subprocess.CompletedProcess) -> bool:
        output = f"{result.stdout}\n{result.stderr}".lower()
        return "1056" in output or "already been started" in output or "already running" in output

    @staticmethod
    def _service_not_running_or_missing(result: subprocess.CompletedProcess) -> bool:
        output = f"{result.stdout}\n{result.stderr}".lower()
        return any(
            marker in output
            for marker in (
                "1060",
                "1062",
                "does not exist",
                "has not been started",
                "不存在",
                "未启动",
            )
        )


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

        executable = Path(sys.executable).resolve()
        self._app_command = [
            str(executable),
            "--background",
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

    program_data = Path(os.environ.get("PROGRAMDATA", r"C:\\ProgramData"))
    log_path = program_data / "BlinkCall" / "logs" / "watchdog.log"
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


def _win_error(operation: str) -> OSError:
    error_code = ctypes.get_last_error() or 1
    return OSError(error_code, f"{operation}: {ctypes.WinError(error_code)}")


def run_watchdog_service() -> int:
    """Run the SCM service entrypoint from ``BlinkCall.exe --watchdog-service``."""
    return WindowsWatchdogService().run()
