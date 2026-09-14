"""Windows Task Scheduler integration for launching BlinkCall at logon."""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from xml.etree import ElementTree


logger = logging.getLogger("blink_call.autostart")


class WindowsAutostartManager:
    """Register BlinkCall as an interactive, all-users logon task."""

    TASK_NAME = "BlinkCall - AutoStart"
    TASK_SCHEMA = "http://schemas.microsoft.com/windows/2004/02/mit/task"
    # S-1-5-4 is the Windows Interactive identity. Group activation runs the
    # task as whichever user has just logged on, rather than as SYSTEM.
    INTERACTIVE_SID = "S-1-5-4"

    @classmethod
    def is_supported(cls) -> bool:
        return sys.platform == "win32"

    @classmethod
    def set_enabled(cls, enabled: bool) -> tuple[bool, str]:
        if not cls.is_supported():
            return False, "Windows Task Scheduler is not available on this platform."
        return cls._register_task() if enabled else cls._delete_task()

    @classmethod
    def _register_task(cls) -> tuple[bool, str]:
        scheduler = cls._scheduler_executable()
        if scheduler is None:
            return False, "schtasks.exe was not found."

        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                suffix=".xml",
                prefix="blink_call_task_",
                delete=False,
            ) as task_file:
                task_file.write(cls._build_task_xml())
                temp_path = task_file.name

            result = cls._run_scheduler_command(
                scheduler,
                "/Create",
                "/TN",
                cls.TASK_NAME,
                "/XML",
                temp_path,
                "/F",
            )
            if result.returncode == 0:
                logger.info("autostart_enabled task=%s", cls.TASK_NAME)
                return True, ""
            return False, cls._format_command_error(result)
        except OSError as exc:
            logger.exception("autostart_register_failed")
            return False, str(exc)
        finally:
            if temp_path:
                try:
                    Path(temp_path).unlink()
                except OSError:
                    logger.warning("autostart_temp_file_cleanup_failed path=%s", temp_path)

    @classmethod
    def _delete_task(cls) -> tuple[bool, str]:
        scheduler = cls._scheduler_executable()
        if scheduler is None:
            return False, "schtasks.exe was not found."

        try:
            result = cls._run_scheduler_command(
                scheduler,
                "/Delete",
                "/TN",
                cls.TASK_NAME,
                "/F",
            )
            if result.returncode == 0 or cls._task_not_found(result):
                logger.info("autostart_disabled task=%s", cls.TASK_NAME)
                return True, ""
            return False, cls._format_command_error(result)
        except OSError as exc:
            logger.exception("autostart_delete_failed")
            return False, str(exc)

    @classmethod
    def _build_task_xml(cls) -> str:
        command, arguments, working_directory = cls._launch_spec()
        namespace = f"{{{cls.TASK_SCHEMA}}}"
        ElementTree.register_namespace("", cls.TASK_SCHEMA)

        root = ElementTree.Element(f"{namespace}Task", {"version": "1.4"})
        registration = ElementTree.SubElement(root, f"{namespace}RegistrationInfo")
        ElementTree.SubElement(registration, f"{namespace}Author").text = "BlinkCall"
        ElementTree.SubElement(registration, f"{namespace}Description").text = (
            "Starts BlinkCall in the interactive session of any user who logs on."
        )

        triggers = ElementTree.SubElement(root, f"{namespace}Triggers")
        logon_trigger = ElementTree.SubElement(triggers, f"{namespace}LogonTrigger")
        ElementTree.SubElement(logon_trigger, f"{namespace}Enabled").text = "true"
        ElementTree.SubElement(logon_trigger, f"{namespace}Delay").text = "PT15S"

        principals = ElementTree.SubElement(root, f"{namespace}Principals")
        principal = ElementTree.SubElement(
            principals,
            f"{namespace}Principal",
            {"id": "BlinkCallInteractiveUser"},
        )
        ElementTree.SubElement(principal, f"{namespace}GroupId").text = cls.INTERACTIVE_SID
        ElementTree.SubElement(principal, f"{namespace}LogonType").text = "Group"
        ElementTree.SubElement(principal, f"{namespace}RunLevel").text = "LeastPrivilege"

        settings = ElementTree.SubElement(root, f"{namespace}Settings")
        ElementTree.SubElement(settings, f"{namespace}MultipleInstancesPolicy").text = "IgnoreNew"
        ElementTree.SubElement(settings, f"{namespace}DisallowStartIfOnBatteries").text = "false"
        ElementTree.SubElement(settings, f"{namespace}StopIfGoingOnBatteries").text = "false"
        ElementTree.SubElement(settings, f"{namespace}AllowHardTerminate").text = "true"
        ElementTree.SubElement(settings, f"{namespace}StartWhenAvailable").text = "true"
        ElementTree.SubElement(settings, f"{namespace}ExecutionTimeLimit").text = "PT0S"
        restart = ElementTree.SubElement(settings, f"{namespace}RestartOnFailure")
        ElementTree.SubElement(restart, f"{namespace}Interval").text = "PT1M"
        ElementTree.SubElement(restart, f"{namespace}Count").text = "3"

        actions = ElementTree.SubElement(
            root,
            f"{namespace}Actions",
            {"Context": "BlinkCallInteractiveUser"},
        )
        execute = ElementTree.SubElement(actions, f"{namespace}Exec")
        ElementTree.SubElement(execute, f"{namespace}Command").text = str(command)
        if arguments:
            ElementTree.SubElement(execute, f"{namespace}Arguments").text = arguments
        ElementTree.SubElement(execute, f"{namespace}WorkingDirectory").text = str(working_directory)

        return ElementTree.tostring(root, encoding="unicode", xml_declaration=True)

    @staticmethod
    def _launch_spec() -> tuple[Path, str, Path]:
        executable = Path(sys.executable).resolve()
        if getattr(sys, "frozen", False) or executable.name.lower() == "blinkcall.exe":
            return executable, "--background", executable.parent

        project_root = Path(__file__).resolve().parents[2]
        return executable, "-m blink_call.setup_app --background", project_root

    @staticmethod
    def _scheduler_executable() -> str | None:
        windows_dir = os.environ.get("WINDIR")
        candidates = []
        if windows_dir:
            candidates.append(Path(windows_dir) / "System32" / "schtasks.exe")
        candidates.append(Path("schtasks.exe"))

        for candidate in candidates:
            if candidate.is_file() or not candidate.is_absolute():
                return str(candidate)
        return None

    @staticmethod
    def _run_scheduler_command(scheduler: str, *arguments: str) -> subprocess.CompletedProcess:
        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        return subprocess.run(
            [scheduler, *arguments],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            creationflags=creation_flags,
        )

    @staticmethod
    def _format_command_error(result: subprocess.CompletedProcess) -> str:
        output = (result.stderr or result.stdout or "").strip()
        return output or f"schtasks.exe failed with exit code {result.returncode}."

    @staticmethod
    def _task_not_found(result: subprocess.CompletedProcess) -> bool:
        output = f"{result.stdout}\n{result.stderr}".lower()
        return any(
            marker in output
            for marker in (
                "does not exist",
                "cannot find",
                "找不到",
                "不存在",
            )
        )
