"""Check that a standalone Windows build opens its main window without Python."""

import ctypes
import subprocess
import sys
import time
from ctypes import wintypes
from pathlib import Path


def main():
    if sys.platform != "win32":
        raise RuntimeError("This startup check requires Windows.")
    distribution = Path(sys.argv[1]).resolve()
    executable = distribution / "BlinkCall.exe"
    version = (distribution / "VERSION").read_text(encoding="utf-8").strip()
    subprocess.run(
        [str(executable), "--play-stage-prompt", str(distribution / "assets/audio/prompt.wav"), "0"],
        cwd=distribution,
        timeout=30,
        check=True,
    )

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
    user32.EnumWindows.restype = wintypes.BOOL
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]

    log_path = distribution.parent / "smoke-test.log"
    with log_path.open("w", encoding="utf-8") as log:
        process = subprocess.Popen([str(executable)], cwd=distribution, stdout=log, stderr=log)
        try:
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError(f"Application exited before opening its window: {process.returncode}")
                titles = []

                @callback_type
                def visit(window, _):
                    pid = wintypes.DWORD()
                    user32.GetWindowThreadProcessId(window, ctypes.byref(pid))
                    if pid.value == process.pid and user32.IsWindowVisible(window):
                        title = ctypes.create_unicode_buffer(512)
                        user32.GetWindowTextW(window, title, len(title))
                        titles.append(title.value)
                    return True

                user32.EnumWindows(visit, 0)
                if any(f"v{version}" in title for title in titles):
                    time.sleep(3)
                    if process.poll() is not None:
                        raise RuntimeError("Application exited immediately after opening its window.")
                    print(f"Windows startup check passed: visible v{version} main window.")
                    return
                time.sleep(0.5)
            raise RuntimeError("Application did not open its main window within 60 seconds.")
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=10)


if __name__ == "__main__":
    main()
