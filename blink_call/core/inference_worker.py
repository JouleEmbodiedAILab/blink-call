import hashlib
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from blink_call.algorithm import EyeRegionDetector, EyeStateClassifier
from blink_call.utils.helper import Helper


class InferenceWorker(QThread):
    result_ready = Signal(dict)
    show_debug_msg = Signal(str)
    eye_region_status = Signal(str)

    def __init__(self, home_model):
        super().__init__()
        self.home_model = home_model

    def initialize_vars(self, config):
        self.blink_pattern = config["pattern"]
        self.debug_info(f"[InferenceWorker] blink_pattern: {self.blink_pattern}")

        self.eye_region_detector = EyeRegionDetector(config["eye_region_detection_algorithm"])
        classifier_config = config["eye_state_classification_algorithm"] or {}
        self.eye_state_classifier = EyeStateClassifier(classifier_config)
        self.classifier_input_roi_scale = float(classifier_config.get("classifier_input_roi_scale", 1.3))
        if self.classifier_input_roi_scale < 1.0:
            raise ValueError("classifier_input_roi_scale must be >= 1.0")
        self.model_identity = self.collect_model_identity()

        self.running = True
        self.min_interval = 1.0 / 10.0
        self.last_time = 0.0
        self.last_missing_frame_debug_s = -float("inf")

        self.stat_fps_interval = 10.0
        self.infer_fps_window_start = time.perf_counter()
        self.infer_fps_counter = 0

        self.latest_eye_bbox = None
        self.latest_face_bbox = None
        self.latest_landmarks = None
        self.latest_eye_region_status = "inference_error"
        self.latest_eye_region_source_timestamp_ms = None
        self.latest_eye_region_sample_timestamp_s = None
        self.latest_detection_elapsed_ms = None
        self.pending_eye_region_future = None
        self.eye_region_executor = None
        self.debug_emit_interval_s = 1.0
        self.last_eye_region_debug_emit_s = time.perf_counter()
        self.last_eye_state_debug_emit_s = time.perf_counter()

        self.match_cooldown_s = 1.0
        self.last_match_time = -1.0

        self.progress_step_idx = 0
        self.progress_in_step_s = 0.0
        self.transition_buffer_s = 3.0
        self.in_transition_buffer = False
        self.transition_deadline_s = None

        self.valid_eye_states = ("open", "closed")
        self.state_window_pass_ratio = 0.9
        self.state_window_start_s = None
        self.state_window_samples = []
        self.state_window_debug_info = "state_window=idle"
        self.last_stable_eye_state = None

    @staticmethod
    def file_sha256(path, chunk_size=1024 * 1024):
        digest = hashlib.sha256()
        with Path(path).open("rb") as handle:
            while chunk := handle.read(chunk_size):
                digest.update(chunk)
        return digest.hexdigest()

    def collect_model_identity(self):
        """Hash the exact detector/landmarker files opened by this worker."""
        identities = {}
        model_paths = {
            "yolov6": getattr(self.eye_region_detector, "yolov6_onnx_path", None),
            "hrnet": getattr(self.eye_region_detector, "hrnet_onnx_path", None),
        }
        for name, raw_path in model_paths.items():
            if not raw_path:
                continue
            path = Path(raw_path).resolve()
            try:
                identity = {
                    "path": str(path),
                    "size_bytes": path.stat().st_size,
                    "sha256": self.file_sha256(path),
                }
                identities[name] = identity
                self.debug_info(
                    f"[InferenceWorker] {name}_model: path={identity['path']}, "
                    f"size_bytes={identity['size_bytes']}, sha256={identity['sha256']}"
                )
            except Exception as exc:
                identities[name] = {"path": str(path), "error": str(exc)}
                self.debug_info(f"[InferenceWorker] {name}_model_identity_error: path={path}, error={exc}")
        return identities

    def reset_progress_state(self):
        self.progress_step_idx = 0
        self.progress_in_step_s = 0.0
        self.in_transition_buffer = False
        self.transition_deadline_s = None
        self.state_window_start_s = None
        self.state_window_samples = []
        self.state_window_debug_info = "state_window=idle; progress_reset=true"
        self.last_stable_eye_state = None

    def debug_info(self, text, source=""):
        now = time.perf_counter()

        if source == "eye_region":
            if now - self.last_eye_region_debug_emit_s >= self.debug_emit_interval_s:
                self.last_eye_region_debug_emit_s = now
                self.show_debug_msg.emit(text)

        elif source == "eye_state":
            if now - self.last_eye_state_debug_emit_s >= self.debug_emit_interval_s:
                self.last_eye_state_debug_emit_s = now
                self.show_debug_msg.emit(text)

        else:
            self.show_debug_msg.emit(text)

    def stat_fps(self):
        self.infer_fps_counter += 1

        now = time.perf_counter()
        elapsed = now - self.infer_fps_window_start

        if elapsed >= self.stat_fps_interval:
            infer_fps = self.infer_fps_counter / elapsed
            self.debug_info(f"[InferenceWorker] inference_fps: {infer_fps:.2f}")

            self.infer_fps_window_start = now
            self.infer_fps_counter = 0

    def stop(self):
        self.running = False

    def run(self):
        try:
            while self.running:
                now = time.perf_counter()
                if now - self.last_time < self.min_interval:
                    time.sleep(self.min_interval / 10.0)
                    continue
                self.last_time = now

                frame = self.home_model.read_frame()[1]
                if frame is None:
                    if now - self.last_missing_frame_debug_s >= 5.0:
                        self.last_missing_frame_debug_s = now
                        self.debug_info("[InferenceWorker] WARNING: frame is None")
                    continue

                source_timestamp_ms = int(time.time() * 1000)
                sample_timestamp_s = time.perf_counter()
                result = self.inference(
                    frame,
                    source_timestamp_ms=source_timestamp_ms,
                    sample_timestamp_s=sample_timestamp_s,
                )
                if not self.running:
                    break
                self.result_ready.emit(result)
                self.stat_fps()
        finally:
            self._shutdown_eye_region_executor()

    def inference(self, frame, source_timestamp_ms=None, sample_timestamp_s=None):
        """Classify at 10 Hz while eye-region detection runs asynchronously.

        At most one detector task may be in flight. The classifier never waits
        for YOLO/HRNet and crops the current frame with the latest completed eye
        box, so detector latency cannot directly throttle classification.
        """
        if source_timestamp_ms is None:
            source_timestamp_ms = int(time.time() * 1000)
        if sample_timestamp_s is None:
            sample_timestamp_s = time.perf_counter()
        inference_started_timestamp_ms = int(time.time() * 1000)
        inference_started = time.perf_counter()

        self.poll_latest_eye_region_result()
        self.submit_eye_region_detect_task(
            frame,
            source_timestamp_ms=source_timestamp_ms,
            sample_timestamp_s=sample_timestamp_s,
        )

        detector_eye_bbox = self.latest_eye_bbox
        classifier_eye_bbox = self._get_classifier_input_bbox(
            frame.shape,
            detector_eye_bbox,
            self.classifier_input_roi_scale,
        )
        eye_roi = Helper.image_cropping(frame, classifier_eye_bbox)
        classification_started = time.perf_counter()
        cls_result = self.eye_state_classifier.classify(
            eye_roi,
            debug_context={
                "eye_bbox_xyxy": classifier_eye_bbox,
                "detector_eye_bbox_xyxy": detector_eye_bbox,
                "face_bbox_xyxy": self.latest_face_bbox,
                "frame_shape": list(frame.shape),
                "classifier_input_roi_scale": self.classifier_input_roi_scale,
            },
        )
        classification_elapsed_ms = (time.perf_counter() - classification_started) * 1000.0
        self.debug_info(f"[EyeStateClassifier] debug info: {cls_result.get('debug_info', '')}", "eye_state")

        raw_eye_state = cls_result.get("state")
        eye_state = self.normalize_eye_state(raw_eye_state)
        model_label = cls_result.get("model_label")
        model_confidence = cls_result.get("model_confidence")
        confidence = cls_result.get("confidence")
        progress_ratio, blinck_call_flag, stage_sound_prompt_flag = self.update_forward_progress(
            eye_state,
            sample_timestamp_s=sample_timestamp_s,
        )
        inference_elapsed_ms = (time.perf_counter() - inference_started) * 1000.0
        inference_finished_timestamp_ms = int(time.time() * 1000)
        confidence_text = "None" if confidence is None else f"{float(confidence):.3f}"
        model_confidence_text = (
            "None" if model_confidence is None else f"{float(model_confidence):.3f}"
        )
        detection_elapsed_ms = self.latest_detection_elapsed_ms
        detection_elapsed_text = "None" if detection_elapsed_ms is None else f"{detection_elapsed_ms:.1f}"
        eye_region_age_ms = None
        if self.latest_eye_region_sample_timestamp_s is not None:
            eye_region_age_ms = max(
                0.0,
                (sample_timestamp_s - self.latest_eye_region_sample_timestamp_s) * 1000.0,
            )
        eye_region_age_text = "None" if eye_region_age_ms is None else f"{eye_region_age_ms:.1f}"

        result = {
            "timestamp_ms": inference_finished_timestamp_ms,
            "source_timestamp_ms": int(source_timestamp_ms),
            "inference_started_timestamp_ms": inference_started_timestamp_ms,
            "inference_finished_timestamp_ms": inference_finished_timestamp_ms,
            "inference_elapsed_ms": float(inference_elapsed_ms),
            "debug_detection_elapsed_ms": detection_elapsed_ms,
            "debug_classification_elapsed_ms": float(classification_elapsed_ms),
            "debug_eye_region_status": self.latest_eye_region_status,
            "debug_eye_region_source_timestamp_ms": self.latest_eye_region_source_timestamp_ms,
            "debug_eye_region_age_ms": eye_region_age_ms,
            "debug_eye_region_detection_pending": self.pending_eye_region_future is not None,
            "blinck_call_flag": bool(blinck_call_flag),
            "stage_sound_prompt_flag": bool(stage_sound_prompt_flag),
            "blink_progress_ratio": float(progress_ratio),
            "debug_classifier_state": eye_state,
            "debug_classifier_model_label": model_label,
            "debug_classifier_model_confidence": model_confidence,
            "debug_classifier_confidence": confidence,
            "debug_eye_bbox_xyxy": classifier_eye_bbox,
            "debug_detector_eye_bbox_xyxy": detector_eye_bbox,
            "debug_face_bbox_xyxy": self.latest_face_bbox,
            "debug_landmarks": self.latest_landmarks,
            "debug_model_identity": self.model_identity,
            "debug_info": "\n".join(
                [
                    "frame_pipeline: async_latest_eye_region",
                    f"source_timestamp_ms: {int(source_timestamp_ms)}",
                    f"inference_started_timestamp_ms: {inference_started_timestamp_ms}",
                    f"inference_elapsed_ms: {inference_elapsed_ms:.1f}",
                    f"detection_elapsed_ms: {detection_elapsed_text}",
                    f"eye_region_age_ms: {eye_region_age_text}",
                    f"eye_region_detection_pending: {self.pending_eye_region_future is not None}",
                    f"classification_elapsed_ms: {classification_elapsed_ms:.1f}",
                    f"model_label: {model_label}",
                    f"model_confidence: {model_confidence_text}",
                    f"state: {eye_state}",
                    f"raw_eye_state: {raw_eye_state}",
                    f"confidence: {confidence_text}",
                    f"sample_timestamp_s: {sample_timestamp_s:.6f}",
                    f"pattern_progress: {progress_ratio:.3f}",
                    f"{self.state_window_debug_info}",
                    f"detector_eye_bbox: {detector_eye_bbox}",
                    f"classifier_eye_bbox: {classifier_eye_bbox}",
                    f"classifier_input_roi_scale: {self.classifier_input_roi_scale:.2f}",
                ]
            ),
        }
        return result

    @staticmethod
    def _run_eye_region_detect_task(
        detector,
        frame,
        source_timestamp_ms,
        sample_timestamp_s,
    ):
        started = time.perf_counter()
        result = detector.detect(frame) or {}
        return {
            "result": result,
            "source_timestamp_ms": int(source_timestamp_ms),
            "sample_timestamp_s": float(sample_timestamp_s),
            "elapsed_ms": (time.perf_counter() - started) * 1000.0,
        }

    def poll_latest_eye_region_result(self):
        future = self.pending_eye_region_future
        if future is None or not future.done():
            return False

        self.pending_eye_region_future = None
        try:
            completed = future.result()
        except Exception as exc:
            self._clear_eye_region_result("inference_error")
            self.debug_info(f"[EyeRegionDetector] status=inference_error; eye_region_error: {exc}")
            return False

        self.latest_eye_region_source_timestamp_ms = completed["source_timestamp_ms"]
        self.latest_eye_region_sample_timestamp_s = completed["sample_timestamp_s"]
        self.latest_detection_elapsed_ms = float(completed["elapsed_ms"])
        self._apply_eye_region_result(completed["result"])
        return True

    def submit_eye_region_detect_task(
        self,
        frame,
        source_timestamp_ms=None,
        sample_timestamp_s=None,
    ):
        if self.pending_eye_region_future is not None:
            return False

        if source_timestamp_ms is None:
            source_timestamp_ms = int(time.time() * 1000)
        if sample_timestamp_s is None:
            sample_timestamp_s = time.perf_counter()
        if self.eye_region_executor is None:
            self.eye_region_executor = ThreadPoolExecutor(
                max_workers=1,
                thread_name_prefix="eye-region",
            )

        # Capture the detector object so a fast stop/start cannot make an old
        # task run against a newly initialized detector instance.
        detector = self.eye_region_detector
        self.pending_eye_region_future = self.eye_region_executor.submit(
            self._run_eye_region_detect_task,
            detector,
            frame.copy(),
            source_timestamp_ms,
            sample_timestamp_s,
        )
        return True

    def _shutdown_eye_region_executor(self):
        future = self.pending_eye_region_future
        self.pending_eye_region_future = None
        if future is not None:
            future.cancel()

        executor = self.eye_region_executor
        self.eye_region_executor = None
        if executor is not None:
            executor.shutdown(wait=False, cancel_futures=True)

    @staticmethod
    def _get_classifier_input_bbox(frame_shape, eye_bbox, roi_scale):
        """Return a natural square ROI expanded around the detector eye box."""
        if eye_bbox is None or roi_scale is None:
            return eye_bbox

        height, width = frame_shape[:2]
        x1, y1, x2, y2 = map(float, eye_bbox)
        bbox_width = max(2.0, x2 - x1)
        bbox_height = max(2.0, y2 - y1)
        side = int(round(max(bbox_width, bbox_height) * float(roi_scale)))
        side = min(max(2, side), max(2, min(width - 1, height - 1)))

        center_x = 0.5 * (x1 + x2)
        center_y = 0.5 * (y1 + y2)
        left = int(round(center_x - 0.5 * side))
        top = int(round(center_y - 0.5 * side))
        right = left + side
        bottom = top + side

        if left < 0:
            right -= left
            left = 0
        if top < 0:
            bottom -= top
            top = 0
        if right >= width:
            left -= right - (width - 1)
            right = width - 1
        if bottom >= height:
            top -= bottom - (height - 1)
            bottom = height - 1

        left = max(0, left)
        top = max(0, top)
        return [left, top, max(left + 2, right), max(top + 2, bottom)]

    def detect_eye_region(self, frame):
        """Synchronously detect and apply a region for direct callers/tests."""
        started = time.perf_counter()
        try:
            result = self.eye_region_detector.detect(frame) or {}
        except Exception as exc:
            self._clear_eye_region_result("inference_error")
            self.debug_info(f"[EyeRegionDetector] status=inference_error; eye_region_error: {exc}")
            return

        self.latest_detection_elapsed_ms = (time.perf_counter() - started) * 1000.0
        self._apply_eye_region_result(result)

    def _clear_eye_region_result(self, status):
        self.latest_eye_bbox = None
        self.latest_face_bbox = None
        self.latest_landmarks = None
        self.latest_eye_region_status = status
        self.latest_eye_region_source_timestamp_ms = None
        self.latest_eye_region_sample_timestamp_s = None
        self.latest_detection_elapsed_ms = None
        self.eye_region_status.emit(status)

    def _apply_eye_region_result(self, result):
        """Apply a completed detector payload on the inference QThread."""

        eye_bbox = result.get("eye_bbox_xyxy")
        face_bbox = result.get("face_bbox_xyxy")
        landmarks = result.get("landmarks")
        self.latest_eye_bbox = [int(v) for v in eye_bbox] if eye_bbox is not None and len(eye_bbox) else None
        self.latest_face_bbox = [int(v) for v in face_bbox] if face_bbox is not None and len(face_bbox) else None
        self.latest_landmarks = (
            [[int(point[0]), int(point[1])] for point in landmarks]
            if landmarks is not None and len(landmarks)
            else None
        )
        status = result.get("status")
        if status not in {"ok", "no_face", "keypoints_invalid", "inference_error"}:
            # Keep a safe fallback for detector implementations that return the
            # old payload without an explicit status.
            if not self.latest_face_bbox:
                status = "no_face"
            elif not self.latest_landmarks:
                status = "keypoints_invalid"
            else:
                status = "ok" if self.latest_eye_bbox else "keypoints_invalid"

        self.latest_eye_region_status = status
        self.eye_region_status.emit(status)
        self.debug_info(
            f"[EyeRegionDetector] status={status}; debug info: {result.get('debug_info', '')}",
            "eye_region",
        )

    @staticmethod
    def normalize_eye_state(raw_eye_state):
        if hasattr(raw_eye_state, "value"):
            return raw_eye_state.value
        if raw_eye_state is None:
            return None
        return str(raw_eye_state)

    def _start_state_window(self, eye_state, sample_timestamp_s):
        if self.progress_step_idx >= len(self.blink_pattern):
            return False

        target_state = str(self.blink_pattern[self.progress_step_idx]["state"])
        if eye_state != target_state:
            return False

        self.state_window_start_s = float(sample_timestamp_s)
        self.state_window_samples = ["correct"]
        self.progress_in_step_s = 0.0
        self.state_window_debug_info = (
            f"state_window=collect; target={target_state}; correct_count=1; "
            "incorrect_count=0; not_sure_count=0; sample_count=1; anchor=true"
        )
        return True

    def _record_state_window_sample(self, eye_state):
        """Put every in-window classification into one of three vote buckets."""
        target_state = str(self.blink_pattern[self.progress_step_idx]["state"])
        if eye_state == target_state:
            category = "correct"
        elif eye_state in self.valid_eye_states:
            category = "incorrect"
        else:
            # not_sure is the model's normal uncertainty result. Missing ROI,
            # not_exist and inference errors are conservatively counted in the
            # same denominator rather than silently improving the pass ratio.
            category = "not_sure"
        self.state_window_samples.append(category)
        return category

    def _finish_state_window(self):
        target_state = str(self.blink_pattern[self.progress_step_idx]["state"])
        sample_count = len(self.state_window_samples)
        correct_count = self.state_window_samples.count("correct")
        incorrect_count = self.state_window_samples.count("incorrect")
        not_sure_count = self.state_window_samples.count("not_sure")
        correct_ratio = correct_count / sample_count if sample_count else 0.0
        passed = sample_count > 0 and correct_ratio >= self.state_window_pass_ratio
        window_start_s = self.state_window_start_s
        self.state_window_start_s = None
        self.state_window_samples = []
        self.progress_in_step_s = 0.0
        self.state_window_debug_info = (
            f"state_window={'passed' if passed else 'failed'}; target={target_state}; "
            f"correct_count={correct_count}; incorrect_count={incorrect_count}; "
            f"not_sure_count={not_sure_count}; sample_count={sample_count}; "
            f"correct_ratio={correct_ratio:.3f}; required_ratio={self.state_window_pass_ratio:.3f}"
        )
        if passed:
            self.last_stable_eye_state = target_state
        return passed, window_start_s

    def update_forward_progress(self, eye_state, sample_timestamp_s=None):
        now = time.perf_counter() if sample_timestamp_s is None else float(sample_timestamp_s)
        stage_sound_prompt_flag = False

        if not self.blink_pattern:
            self.reset_progress_state()
            return 0.0, False, False

        eye_state = self.normalize_eye_state(eye_state)
        first_state = str(self.blink_pattern[0]["state"])

        if self.state_window_start_s is not None:
            rule_duration = max(0.0, float(self.blink_pattern[self.progress_step_idx]["duration_s"]))
            window_end_s = self.state_window_start_s + rule_duration
            target_state = str(self.blink_pattern[self.progress_step_idx]["state"])

            if now < window_end_s:
                self._record_state_window_sample(eye_state)
                self.progress_in_step_s = max(0.0, now - self.state_window_start_s)
                correct_count = self.state_window_samples.count("correct")
                incorrect_count = self.state_window_samples.count("incorrect")
                not_sure_count = self.state_window_samples.count("not_sure")
                sample_count = len(self.state_window_samples)
                correct_ratio = correct_count / sample_count
                self.state_window_debug_info = (
                    f"state_window=collect; target={target_state}; "
                    f"correct_count={correct_count}; incorrect_count={incorrect_count}; "
                    f"not_sure_count={not_sure_count}; sample_count={sample_count}; "
                    f"correct_ratio={correct_ratio:.3f}"
                )
            else:
                # The current observation is at or beyond the deadline, so it
                # is available for the next state but is not part of this window.
                passed, window_start_s = self._finish_state_window()
                if not passed:
                    self.reset_progress_state()
                    if eye_state == first_state:
                        self._start_state_window(eye_state, now)
                    return self.current_progress_ratio(self.blink_pattern), False, False

                completed_rule = self.blink_pattern[self.progress_step_idx]
                stage_sound_prompt_flag = bool(completed_rule.get("sound_prompt"))
                logging.getLogger("blink_call.audio").info(
                    "blink_stage_completed step=%s total_steps=%s state=%s sound_prompt=%s",
                    self.progress_step_idx + 1,
                    len(self.blink_pattern),
                    completed_rule.get("state"),
                    stage_sound_prompt_flag,
                )
                self.progress_step_idx += 1

                if self.progress_step_idx >= len(self.blink_pattern):
                    ratio = 1.0
                    blink = (now - self.last_match_time) >= self.match_cooldown_s
                    if blink:
                        self.last_match_time = now
                        self.reset_progress_state()
                    return ratio, blink, stage_sound_prompt_flag

                self.in_transition_buffer = True
                self.transition_deadline_s = window_start_s + rule_duration + self.transition_buffer_s
                if now >= self.transition_deadline_s:
                    self.reset_progress_state()
                    if eye_state == first_state:
                        self._start_state_window(eye_state, now)
                elif eye_state == str(self.blink_pattern[self.progress_step_idx]["state"]):
                    self.in_transition_buffer = False
                    self.transition_deadline_s = None
                    self._start_state_window(eye_state, now)

        elif self.in_transition_buffer:
            if now >= self.transition_deadline_s:
                self.reset_progress_state()
                if eye_state == first_state:
                    self._start_state_window(eye_state, now)
            elif eye_state == str(self.blink_pattern[self.progress_step_idx]["state"]):
                self.in_transition_buffer = False
                self.transition_deadline_s = None
                self._start_state_window(eye_state, now)

        elif eye_state == first_state:
            # Startup is intentionally level-triggered: an already active
            # first state starts a new attempt immediately.
            self._start_state_window(eye_state, now)

        ratio = self.current_progress_ratio(self.blink_pattern)
        return ratio, False, stage_sound_prompt_flag

    def current_progress_ratio(self, pattern):
        if self.progress_step_idx >= len(pattern):
            return 1.0

        total = sum(float(item["duration_s"]) for item in pattern)

        completed = 0.0
        for idx in range(self.progress_step_idx):
            completed += float(pattern[idx]["duration_s"])

        return min(1.0, max(0.0, (completed + self.progress_in_step_s) / total))
