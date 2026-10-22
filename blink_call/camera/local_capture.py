import logging
import sys
import threading
import time
from enum import Enum

import cv2


logger = logging.getLogger("blink_call.camera")


class CaptureState(str, Enum):
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    DEGRADED = "degraded"
    RECONNECTING = "reconnecting"
    STOPPING = "stopping"


class LocalCameraCapture:
    def __init__(
        self,
        camera_id: int = 0,
        interval: float = 0.01,
        *,
        fallback_camera_id=None,
        fallback_enabled: bool = False,
        failure_threshold: int = 5,
        failure_duration_s: float = 0.5,
        fallback_after_s: float = 5.0,
        primary_recovery_stability_s: float = 10.0,
        stale_frame_timeout_s: float = 1.0,
        reconnect_backoff_s=(0.5, 1.0, 2.0, 5.0),
        stop_timeout_s: float = 2.0,
        startup_timeout_s: float = 3.0,
    ):
        self.camera_id = int(camera_id)
        self.interval = max(0.0, float(interval))
        self.fallback_camera_id = None if fallback_camera_id is None else int(fallback_camera_id)
        self.fallback_enabled = bool(
            fallback_enabled
            and self.fallback_camera_id is not None
            and self.fallback_camera_id != self.camera_id
        )
        self.failure_threshold = max(1, int(failure_threshold))
        self.failure_duration_s = max(0.0, float(failure_duration_s))
        self.fallback_after_s = max(0.0, float(fallback_after_s))
        self.primary_recovery_stability_s = max(0.0, float(primary_recovery_stability_s))
        self.stale_frame_timeout_s = max(0.0, float(stale_frame_timeout_s))
        self.reconnect_backoff_s = tuple(max(0.0, float(value)) for value in reconnect_backoff_s) or (0.5,)
        self.stop_timeout_s = max(0.0, float(stop_timeout_s))
        self.startup_timeout_s = max(0.0, float(startup_timeout_s))
        # CAP_ANY normally selects MSMF on Windows. Some cameras open through
        # that backend but never deliver frames, so try DirectShow first and
        # rotate backends if an opened handle cannot produce its first frame.
        self._camera_backends = (
            (cv2.CAP_DSHOW, cv2.CAP_MSMF, cv2.CAP_ANY)
            if sys.platform == "win32" else (cv2.CAP_ANY,)
        )
        self._backend_indices = {}

        self.cap = None
        self.running = False
        self.latest_frame = None
        # Consumers must not mistake a frozen snapshot for a live camera feed.
        self._latest_frame_at = None

        self._camera_found = False
        self._state = CaptureState.STOPPED
        self._active_camera_id = None
        self._using_fallback = False
        self._consecutive_failures = 0
        self._last_success_at = None
        self._last_error = None

        self._frame_lock = threading.Lock()
        # Backward-compatible alias for older callers/tests that use ``_lock``.
        self._lock = self._frame_lock
        self._status_lock = threading.Lock()
        self._cap_lock = threading.Lock()
        self._lifecycle_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread = None

    @property
    def camera_found(self):
        with self._status_lock:
            return self._camera_found

    @property
    def state(self):
        with self._status_lock:
            return self._state

    @property
    def active_camera_id(self):
        with self._status_lock:
            return self._active_camera_id

    @property
    def using_fallback(self):
        with self._status_lock:
            return self._using_fallback

    def get_status(self):
        with self._status_lock:
            last_success_age_s = None
            if self._last_success_at is not None:
                last_success_age_s = max(0.0, time.monotonic() - self._last_success_at)
            state = self._state
            camera_found = self._camera_found
            last_error = self._last_error
            if (
                state == CaptureState.RUNNING
                and self.stale_frame_timeout_s > 0
                and last_success_age_s is not None
                and last_success_age_s >= self.stale_frame_timeout_s
            ):
                state = CaptureState.DEGRADED
                camera_found = False
                last_error = last_error or "camera frame is stale"
            return {
                "state": state.value,
                "camera_found": camera_found,
                "primary_camera_id": self.camera_id,
                "fallback_camera_id": self.fallback_camera_id,
                "active_camera_id": self._active_camera_id,
                "using_fallback": self._using_fallback,
                "consecutive_failures": self._consecutive_failures,
                "last_success_age_s": last_success_age_s,
                "last_error": last_error,
            }

    def start(self):
        with self._lifecycle_lock:
            if self._thread is not None and self._thread.is_alive():
                return self.running

            self._stop_event.clear()
            self.running = True
            self._clear_latest_frame()
            self._update_status(
                state=CaptureState.STARTING,
                camera_found=False,
                active_camera_id=None,
                using_fallback=False,
                consecutive_failures=0,
                last_success_at=None,
                last_error=None,
            )
            self._thread = threading.Thread(
                target=self._capture_loop,
                name=f"camera-capture-{self.camera_id}",
                daemon=True,
            )
            self._thread.start()

        logger.info(
            "camera_start primary_id=%s fallback_enabled=%s fallback_id=%s",
            self.camera_id,
            self.fallback_enabled,
            self.fallback_camera_id,
        )
        # Starting the supervisor is success. Camera readiness is exposed by
        # ``state``/``camera_found`` and may become true after a later hot-plug.
        return True

    def _capture_loop(self):
        target_camera_id = self.camera_id
        target_unavailable_since = None
        outage_started_at = None
        backoff_index = 0
        open_attempt = 0
        # A successful reopen is only provisional. Keep the original primary
        # outage time until the camera has delivered frames continuously for
        # the stability window, so a flapping primary can reach the fallback.
        primary_unstable_since = None
        primary_recovery_started_at = None

        try:
            while not self._stop_event.is_set():
                open_attempt += 1
                open_started_at = time.monotonic()
                cap, open_error = self._open_camera(target_camera_id, open_attempt)
                if cap is None:
                    now = time.monotonic()
                    target_unavailable_since = target_unavailable_since or open_started_at
                    outage_started_at = outage_started_at or open_started_at
                    if target_camera_id == self.camera_id:
                        primary_unstable_since = primary_unstable_since or open_started_at
                        primary_recovery_started_at = None
                    self._mark_reconnecting(target_camera_id, open_error)

                    fallback_reference_at = (
                        primary_unstable_since
                        if target_camera_id == self.camera_id
                        else target_unavailable_since
                    )
                    switched_id = self._fallback_target_if_due(
                        target_camera_id,
                        fallback_reference_at,
                        now,
                    )
                    if switched_id != target_camera_id:
                        target_camera_id = switched_id
                        target_unavailable_since = now
                        if target_camera_id == self.camera_id:
                            primary_unstable_since = now
                            primary_recovery_started_at = None
                        backoff_index = 0
                        continue

                    delay = self._get_retry_delay(
                        backoff_index,
                        target_unavailable_since,
                        now,
                    )
                    backoff_index += 1
                    logger.warning(
                        "camera_reopen_failed camera_id=%s attempt=%s retry_in_s=%.2f error=%s",
                        target_camera_id,
                        open_attempt,
                        delay,
                        open_error,
                    )
                    self._stop_event.wait(delay)
                    continue

                self._store_cap(cap)
                backend_name = self._get_backend_name(cap)
                logger.info(
                    "camera_opened camera_id=%s attempt=%s backend=%s using_fallback=%s",
                    target_camera_id,
                    open_attempt,
                    backend_name,
                    target_camera_id != self.camera_id,
                )
                self._update_status(
                    state=CaptureState.STARTING if outage_started_at is None else CaptureState.RECONNECTING,
                    camera_found=False,
                    active_camera_id=target_camera_id,
                    using_fallback=target_camera_id != self.camera_id,
                    consecutive_failures=0,
                    last_error=None,
                )

                first_failure_at = None
                frame_received_from_handle = False
                first_frame_started_at = time.monotonic()
                try:
                    while not self._stop_event.is_set():
                        read_started_at = time.monotonic()
                        ok, frame, read_error = self._read_camera(cap)
                        now = time.monotonic()

                        if ok and frame is not None:
                            frame_received_from_handle = True
                            if outage_started_at is not None:
                                logger.info(
                                    "camera_recovered camera_id=%s outage_ms=%s backend=%s using_fallback=%s",
                                    target_camera_id,
                                    int((now - outage_started_at) * 1000),
                                    backend_name,
                                    target_camera_id != self.camera_id,
                                )
                            outage_started_at = None
                            target_unavailable_since = None
                            first_failure_at = None
                            backoff_index = 0
                            if target_camera_id == self.camera_id and primary_unstable_since is not None:
                                primary_recovery_started_at = primary_recovery_started_at or now
                                stable_for_s = now - primary_recovery_started_at
                                if stable_for_s >= self.primary_recovery_stability_s:
                                    logger.info(
                                        "camera_primary_stable camera_id=%s stable_ms=%s",
                                        target_camera_id,
                                        int(stable_for_s * 1000),
                                    )
                                    primary_unstable_since = None
                                    primary_recovery_started_at = None
                            self._store_successful_frame(frame, target_camera_id, now)
                            self._stop_event.wait(self.interval)
                            continue

                        outage_started_at = outage_started_at or read_started_at
                        first_failure_at = first_failure_at or read_started_at
                        target_unavailable_since = target_unavailable_since or read_started_at
                        if target_camera_id == self.camera_id:
                            primary_unstable_since = primary_unstable_since or read_started_at
                            primary_recovery_started_at = None
                        # Opening a camera is not the same as having a frame.
                        # Fast initial read failures must not close the handle
                        # every ~50 ms before the device has time to warm up.
                        if (
                            not frame_received_from_handle
                            and now - first_frame_started_at < self.startup_timeout_s
                        ):
                            self._stop_event.wait(max(self.interval, 0.01))
                            continue
                        failures = self._record_read_failure(read_error)
                        if failures == 1:
                            logger.warning(
                                "camera_read_failed camera_id=%s backend=%s error=%s",
                                target_camera_id,
                                backend_name,
                                read_error,
                            )

                        failure_duration = now - first_failure_at
                        # Some backends block for about a second before one
                        # failed read returns. Duration must therefore be an
                        # alternative to the count threshold, not cumulative.
                        if self._read_failure_requires_reconnect(failures, failure_duration):
                            self._mark_reconnecting(target_camera_id, read_error)
                            logger.warning(
                                "camera_read_reconnect camera_id=%s failures=%s duration_ms=%s",
                                target_camera_id,
                                failures,
                                int(failure_duration * 1000),
                            )
                            break

                        self._stop_event.wait(self.interval)
                finally:
                    self._release_camera(cap, target_camera_id, backend_name)

                if self._stop_event.is_set():
                    break

                if not frame_received_from_handle:
                    self._advance_backend(target_camera_id)

                now = time.monotonic()
                target_unavailable_since = target_unavailable_since or now
                fallback_reference_at = (
                    primary_unstable_since
                    if target_camera_id == self.camera_id
                    else target_unavailable_since
                )
                switched_id = self._fallback_target_if_due(
                    target_camera_id,
                    fallback_reference_at,
                    now,
                )
                if switched_id != target_camera_id:
                    target_camera_id = switched_id
                    target_unavailable_since = now
                    if target_camera_id == self.camera_id:
                        primary_unstable_since = now
                        primary_recovery_started_at = None
                    backoff_index = 0
                elif not frame_received_from_handle:
                    delay = self._get_retry_delay(
                        backoff_index,
                        target_unavailable_since,
                        now,
                    )
                    backoff_index += 1
                    self._stop_event.wait(delay)
        except Exception:
            logger.exception("camera_capture_loop_crashed primary_id=%s", self.camera_id)
        finally:
            self.running = False
            self._clear_latest_frame()
            self._update_status(
                state=CaptureState.STOPPED,
                camera_found=False,
                active_camera_id=None,
                using_fallback=False,
                consecutive_failures=0,
                last_success_at=None,
            )
            logger.info("camera_stopped primary_id=%s", self.camera_id)

    def _open_camera(self, camera_id, attempt):
        error = "camera opening cancelled"
        for _ in self._camera_backends:
            if self._stop_event.is_set():
                break
            backend = self._camera_backends[self._backend_indices.get(camera_id, 0)]
            logger.info(
                "camera_open_attempt camera_id=%s attempt=%s backend=%s",
                camera_id, attempt, backend,
            )
            cap = None
            try:
                cap = (
                    cv2.VideoCapture(camera_id) if backend == cv2.CAP_ANY
                    else cv2.VideoCapture(camera_id, backend)
                )
                if cap is not None and cap.isOpened():
                    return cap, None
                error = "VideoCapture.isOpened() returned false"
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"

            logger.warning(
                "camera_backend_failed camera_id=%s backend=%s error=%s",
                camera_id, backend, error,
            )
            if cap is not None:
                self._safe_release(cap, camera_id, str(backend))
            self._advance_backend(camera_id)
        return None, error

    def _advance_backend(self, camera_id):
        current = self._backend_indices.get(camera_id, 0)
        self._backend_indices[camera_id] = (current + 1) % len(self._camera_backends)

    @staticmethod
    def _read_camera(cap):
        try:
            ok, frame = cap.read()
            if not ok or frame is None or getattr(frame, "size", 1) == 0:
                return False, None, "VideoCapture.read() returned no frame"
            return True, frame, None
        except Exception as exc:
            return False, None, f"{type(exc).__name__}: {exc}"

    def _store_successful_frame(self, frame, camera_id, now):
        with self._frame_lock:
            self.latest_frame = frame
            self._latest_frame_at = now
        self._update_status(
            state=CaptureState.RUNNING,
            camera_found=True,
            active_camera_id=camera_id,
            using_fallback=camera_id != self.camera_id,
            consecutive_failures=0,
            last_success_at=now,
            last_error=None,
        )

    def _record_read_failure(self, error):
        with self._status_lock:
            self._state = CaptureState.DEGRADED
            self._consecutive_failures += 1
            self._last_error = error
            return self._consecutive_failures

    def _read_failure_requires_reconnect(self, failures, failure_duration_s):
        return (
            failures >= self.failure_threshold
            or failure_duration_s >= self.failure_duration_s
        )

    def _mark_reconnecting(self, camera_id, error):
        self._update_status(
            state=CaptureState.RECONNECTING,
            camera_found=False,
            active_camera_id=camera_id,
            using_fallback=camera_id != self.camera_id,
            last_error=error,
        )
        self._clear_latest_frame()

    def _fallback_target_if_due(self, target_camera_id, unavailable_since, now):
        if not self.fallback_enabled or unavailable_since is None:
            return target_camera_id
        if now - unavailable_since < self.fallback_after_s:
            return target_camera_id

        if target_camera_id == self.camera_id:
            next_camera_id = self.fallback_camera_id
            reason = "primary_unavailable"
        else:
            # Do not fail back while the fallback is healthy. If it also goes
            # down, trying the primary again gives the user the best chance of
            # retaining a camera feed.
            next_camera_id = self.camera_id
            reason = "fallback_unavailable"

        logger.warning(
            "camera_switch_target from_id=%s to_id=%s reason=%s unavailable_ms=%s",
            target_camera_id,
            next_camera_id,
            reason,
            int((now - unavailable_since) * 1000),
        )
        return next_camera_id

    def _get_retry_delay(self, backoff_index, unavailable_since, now):
        delay = self.reconnect_backoff_s[min(backoff_index, len(self.reconnect_backoff_s) - 1)]
        if self.fallback_enabled and unavailable_since is not None:
            remaining_before_switch = max(
                0.0,
                self.fallback_after_s - (now - unavailable_since),
            )
            delay = min(delay, remaining_before_switch)
        return delay

    def _store_cap(self, cap):
        with self._cap_lock:
            self.cap = cap

    def _release_camera(self, cap, camera_id, backend_name):
        self._safe_release(cap, camera_id, backend_name)
        with self._cap_lock:
            if self.cap is cap:
                self.cap = None

    @staticmethod
    def _safe_release(cap, camera_id, backend_name):
        started_at = time.monotonic()
        try:
            cap.release()
            logger.info(
                "camera_released camera_id=%s backend=%s duration_ms=%s",
                camera_id,
                backend_name,
                int((time.monotonic() - started_at) * 1000),
            )
        except Exception:
            logger.exception("camera_release_failed camera_id=%s backend=%s", camera_id, backend_name)

    @staticmethod
    def _get_backend_name(cap):
        try:
            return str(cap.getBackendName() or "unknown")
        except Exception:
            return "unknown"

    def _update_status(self, **changes):
        with self._status_lock:
            for name, value in changes.items():
                setattr(self, f"_{name}", value)

    def _clear_latest_frame(self):
        with self._frame_lock:
            self.latest_frame = None
            self._latest_frame_at = None

    def stop(self):
        with self._lifecycle_lock:
            thread = self._thread
            if thread is None or not thread.is_alive():
                self.running = False
                self._thread = None
                self._clear_latest_frame()
                self._update_status(
                    state=CaptureState.STOPPED,
                    camera_found=False,
                    active_camera_id=None,
                    using_fallback=False,
                    last_success_at=None,
                )
                return True

            self.running = False
            self._stop_event.set()
            self._update_status(state=CaptureState.STOPPING)

        logger.info("camera_stop_requested primary_id=%s timeout_s=%.2f", self.camera_id, self.stop_timeout_s)
        if thread is not threading.current_thread():
            thread.join(timeout=self.stop_timeout_s)

        if thread.is_alive():
            self._update_status(last_error=f"camera stop timed out after {self.stop_timeout_s:.2f}s")
            logger.error(
                "camera_stop_timeout primary_id=%s timeout_s=%.2f",
                self.camera_id,
                self.stop_timeout_s,
            )
            return False

        with self._lifecycle_lock:
            if self._thread is thread:
                self._thread = None
        return True

    def read_latest_frame(self):
        with self._frame_lock:
            if self.latest_frame is None:
                return None
            if (
                self.stale_frame_timeout_s > 0
                and self._latest_frame_at is not None
                and time.monotonic() - self._latest_frame_at >= self.stale_frame_timeout_s
            ):
                return None
            return self.latest_frame.copy()
