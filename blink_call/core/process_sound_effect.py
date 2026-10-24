"""Run each Windows stage prompt in a fresh, bounded-lifetime process."""

import logging
import math
import sys
import time
import wave
from pathlib import Path

from PySide6.QtCore import QObject, QProcess, QTimer, Signal, Slot

from blink_call.core.audio_status_logging import log_audio_status
from blink_call.core.resource_path import PROJECT_ROOT
from blink_call.core.stage_prompt_worker import (
    NATIVE_PLAYBACK_TIMEOUT_EXIT_CODE,
    STAGE_PROMPT_ARGUMENT,
)

audio_logger = logging.getLogger("blink_call.audio")


def _playback_command(source_path: Path, volume: float):
    arguments = [STAGE_PROMPT_ARGUMENT, str(source_path), str(volume)]
    launcher = Path(sys.argv[0]).resolve()
    if "__compiled__" in globals() or launcher.name.casefold() == "blinkcall.exe":
        # Nuitka's sys.executable may still identify the build interpreter.
        return str(launcher), arguments
    if getattr(sys, "frozen", False):
        return sys.executable, arguments
    executable = Path(sys.executable)
    if sys.platform == "win32" and executable.name.casefold() == "python.exe":
        windowless = executable.with_name("pythonw.exe")
        if windowless.is_file():
            executable = windowless
    return str(executable), ["-m", "blink_call.setup_app", *arguments]


class ProcessSoundEffect(QObject):
    """Keep at most one child; retriggering replaces it without blocking the UI."""

    diagnostic = Signal(str)

    def __init__(self, source_path: Path, parent=None):
        super().__init__(parent)
        self.source_path = Path(source_path).resolve()
        self._volume = 1.0
        self._request_id = 0
        self._active_request = None
        self._pending_request = None
        self._child_pid = 0
        self._cancel_reason = None
        self._deadline = None
        self._closing = False
        duration_ms = 2000
        try:
            with wave.open(str(self.source_path), "rb") as source:
                duration_ms = math.ceil(source.getnframes() * 1000 / source.getframerate())
        except (OSError, EOFError, wave.Error):
            pass  # The worker reports a missing or invalid source on playback.
        self._timeout_ms = duration_ms + 3000

        self._process = QProcess(self)
        self._process.setWorkingDirectory(str(PROJECT_ROOT))
        self._process.started.connect(self._on_started)
        self._process.finished.connect(self._on_finished)
        self._process.errorOccurred.connect(self._on_error)
        self._timeout_timer = QTimer(self)
        self._timeout_timer.setSingleShot(True)
        self._timeout_timer.timeout.connect(self._on_timeout)

    def set_volume(self, volume: float):
        self._volume = max(0.0, min(1.0, float(volume)))

    def play(self):
        if self._closing:
            return
        if self._volume == 0:
            self.stop()
            self._emit_diagnostic("play_skipped", reason="muted")
            return
        if not self.source_path.is_file():
            self._emit_diagnostic("play_skipped", reason="source_missing", source=self.source_path)
            return
        self._request_id += 1
        self._pending_request = (self._request_id, self._volume)
        self._emit_diagnostic("play_requested", request=self._request_id, volume=self._volume)
        if self._active_request is not None:
            self._cancel_reason = "retriggered"
            self._process.kill()
            # Starting may not yet have created an OS process. _on_started()
            # also checks cancellation, and finished() starts the latest cue.
            return
        self._start_pending()

    def stop(self):
        self._pending_request = None
        if self._active_request is not None:
            self._cancel_reason = "stopped"
            self._emit_diagnostic("play_stopped")
            self._process.kill()

    def shutdown(self):
        self._closing = True
        self.stop()
        if self._process.state() != QProcess.ProcessState.NotRunning:
            if not self._process.waitForFinished(1000):
                self._emit_diagnostic("process_cleanup_pending")
        self._timeout_timer.stop()

    def log_state(self, event: str):
        self._emit_diagnostic(event, state=self._process.state().name, volume=self._volume)

    def _start_pending(self):
        if self._pending_request is None or self._closing:
            return
        self._active_request, volume = self._pending_request
        self._pending_request = None
        self._cancel_reason = None
        self._child_pid = 0
        try:
            program, arguments = _playback_command(self.source_path, volume)
        except Exception as exc:
            self._emit_diagnostic("play_failed", reason="command_failed", error=exc)
            self._active_request = None
            return
        self._deadline = time.monotonic() + self._timeout_ms / 1000.0
        self._timeout_timer.start(self._timeout_ms)
        self._process.start(program, arguments)

    @Slot()
    def _on_started(self):
        self._child_pid = self._process.processId()
        self._emit_diagnostic("process_started")
        if self._cancel_reason is not None:
            self._process.kill()

    @Slot(int, QProcess.ExitStatus)
    def _on_finished(self, exit_code, exit_status):
        if self._active_request is None:
            return
        self._timeout_timer.stop()
        self._deadline = None
        error_text = bytes(self._process.readAllStandardError()).decode("utf-8", errors="replace").strip()
        if self._cancel_reason is not None:
            self._emit_diagnostic("process_reaped", reason=self._cancel_reason)
        elif exit_status == QProcess.ExitStatus.NormalExit and exit_code == 0:
            self._emit_diagnostic("play_finished")
        else:
            reason = "native_playback_timeout" if exit_code == NATIVE_PLAYBACK_TIMEOUT_EXIT_CODE else "worker_failed"
            self._emit_diagnostic("play_failed", reason=reason, exit_code=exit_code, error=error_text)
        self._active_request = None
        self._child_pid = 0
        self._cancel_reason = None
        self._start_pending()

    @Slot(QProcess.ProcessError)
    def _on_error(self, error):
        if error == QProcess.ProcessError.FailedToStart and self._active_request is not None:
            self._timeout_timer.stop()
            self._deadline = None
            self._emit_diagnostic("play_failed", reason="start_failed", error=self._process.errorString())
            self._active_request = None
            self._child_pid = 0
            self._cancel_reason = None
            self._start_pending()

    @Slot()
    def _on_timeout(self):
        if self._active_request is None or self._deadline is None:
            return
        remaining_ms = math.ceil((self._deadline - time.monotonic()) * 1000)
        if remaining_ms > 0:
            self._timeout_timer.start(remaining_ms)
            return
        self._cancel_reason = "playback_timeout"
        self._emit_diagnostic("playback_timeout")
        self._process.kill()

    def _emit_diagnostic(self, event: str, **details):
        details.setdefault("request", self._active_request)
        details["child_pid"] = self._child_pid
        details["backend"] = "winmm_process"
        audio_logger.info("stage_prompt_%s %s", event, details)
        log_audio_status("stage_prompt", event, **details)
        message = "; ".join(f"{key}={value}" for key, value in details.items())
        self.diagnostic.emit(f"[stage_prompt] {event}; {message}")
