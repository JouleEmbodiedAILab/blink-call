"""Keep one BlinkCall GUI process per Windows user session."""

import ctypes
from ctypes import wintypes
import hashlib
import logging
import os
from pathlib import Path
import sys
import time

from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QMessageBox


logger = logging.getLogger("blink_call.lifecycle")
ERROR_ACCESS_DENIED = 5
ERROR_ALREADY_EXISTS = 183


class WindowsSingleInstance:
    def __init__(self, app):
        self._app = app
        self._window = None
        self._activation_pending = False
        self._server = None
        self._mutex = None
        self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._kernel32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
        self._kernel32.CreateMutexW.restype = wintypes.HANDLE
        self._kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        self._kernel32.CloseHandle.restype = wintypes.BOOL
        self._kernel32.ProcessIdToSessionId.argtypes = [wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
        self._kernel32.ProcessIdToSessionId.restype = wintypes.BOOL

        session_id = wintypes.DWORD()
        if not self._kernel32.ProcessIdToSessionId(os.getpid(), ctypes.byref(session_id)):
            raise ctypes.WinError(ctypes.get_last_error())
        executable = str(Path(sys.argv[0]).resolve()).casefold()
        identity = hashlib.sha256(executable.encode("utf-8")).hexdigest()[:24]
        # The mutex is session-local and exclusive; the pipe carries window activation.
        self._mutex_name = f"Local\\BlinkCall-{identity}"
        self._server_name = f"BlinkCall-{identity}-{session_id.value}"

    def acquire(self):
        ctypes.set_last_error(0)
        mutex = self._kernel32.CreateMutexW(None, False, self._mutex_name)
        error = ctypes.get_last_error()
        if not mutex and error not in (ERROR_ALREADY_EXISTS, ERROR_ACCESS_DENIED):
            raise ctypes.WinError(error)
        if error in (ERROR_ALREADY_EXISTS, ERROR_ACCESS_DENIED):
            if mutex:
                self._kernel32.CloseHandle(mutex)
            if not self._activate_existing():
                QMessageBox.warning(
                    None,
                    "BlinkCall",
                    "BlinkCall 已在运行，但无法唤起窗口。\n"
                    "BlinkCall is already running, but its window could not be opened.",
                )
            return False

        self._mutex = mutex
        self._server = QLocalServer(self._app)
        self._server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        self._server.newConnection.connect(self._on_new_connection)
        if not self._server.listen(self._server_name):
            logger.error("single_instance_listen_failed error=%s", self._server.errorString())
        return True

    def bind_window(self, window):
        self._window = window
        if self._activation_pending:
            self._activation_pending = False
            window.show_window()

    def close(self):
        if self._server is not None:
            self._server.close()
        if self._mutex is not None:
            self._kernel32.CloseHandle(self._mutex)
            self._mutex = None

    def _activate_existing(self):
        for _ in range(10):
            socket = QLocalSocket()
            socket.connectToServer(self._server_name)
            if socket.waitForConnected(100) and socket.waitForReadyRead(500):
                acknowledged = bytes(socket.readAll()) == b"ok"
                socket.disconnectFromServer()
                if acknowledged:
                    return True
            time.sleep(0.1)
        return False

    def _on_new_connection(self):
        while self._server.hasPendingConnections():
            socket = self._server.nextPendingConnection()
            socket.write(b"ok")
            socket.disconnectFromServer()
            socket.deleteLater()
        if self._window is None:
            self._activation_pending = True
        else:
            self._window.show_window()
