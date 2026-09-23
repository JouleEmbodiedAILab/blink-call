import threading
import time
import urllib.error
import urllib.request

import cv2
import numpy as np


class RemoteCameraClient:
    def __init__(
        self,
        ip: str,
        port: int,
        timeout: float = 3,
        interval: float = 0.03,
        stale_frame_timeout_s: float = 1.0,
    ):
        self.ip = ip
        self.port = port
        self.timeout = timeout
        self.interval = interval
        self.stale_frame_timeout_s = max(0.0, float(stale_frame_timeout_s))

        self.running = False
        self.latest_frame = None
        self._status_code = 0
        self._latest_frame_at = None

        self._lock = threading.Lock()
        self._thread = None

    @property
    def frame_url(self):
        return f"http://{self.ip}:{self.port}/frame"

    @property
    def status_code(self):
        with self._lock:
            if (
                self.latest_frame is not None
                and self._latest_frame_at is not None
                and self.stale_frame_timeout_s > 0
                and time.monotonic() - self._latest_frame_at >= self.stale_frame_timeout_s
            ):
                return -4
            return self._status_code

    def set_response(self, status_code, frame):
        with self._lock:
            self._status_code = status_code
            self.latest_frame = frame
            self._latest_frame_at = time.monotonic() if frame is not None else None

    def start(self):
        if self.running:
            return True

        self.running = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()
        return True

    def _poll_loop(self):
        while self.running:
            time.sleep(self.interval)

            try:
                with urllib.request.urlopen(self.frame_url, timeout=self.timeout) as resp:
                    content_type = (resp.headers.get("Content-Type") or "").lower()
                    payload = resp.read()

                if "image/jpeg" not in content_type:
                    self.set_response(499, None)
                    continue

                image_data = np.frombuffer(payload, dtype=np.uint8)
                frame = cv2.imdecode(image_data, cv2.IMREAD_COLOR)
                if frame is None:
                    self.set_response(498, None)
                else:
                    self.set_response(200, frame)
            except urllib.error.HTTPError as exc:
                self.set_response(exc.code, None)
            except urllib.error.URLError:
                self.set_response(-1, None)
            except TimeoutError:
                self.set_response(-2, None)
            except OSError:
                self.set_response(-3, None)
            except Exception:
                self.set_response(-999, None)

    def stop(self):
        self.running = False

    def read_latest_frame(self):
        with self._lock:
            if self.latest_frame is None:
                return None
            if (
                self._latest_frame_at is None
                or (
                    self.stale_frame_timeout_s > 0
                    and time.monotonic() - self._latest_frame_at >= self.stale_frame_timeout_s
                )
            ):
                return None
            return self.latest_frame.copy()
