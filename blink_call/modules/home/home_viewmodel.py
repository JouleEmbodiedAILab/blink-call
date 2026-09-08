import logging
import time
from datetime import datetime
from pathlib import Path

import cv2
from PySide6.QtCore import QObject, QTimer, QUrl, Signal
from PySide6.QtGui import QImage
from PySide6.QtMultimedia import QSoundEffect

from blink_call.core.inference_worker import InferenceWorker
from blink_call.core.model_files_manager import ModelFilesManager
from blink_call.core.recovering_sound_effect import RecoveringSoundEffect
from blink_call.core.resource_path import get_resource_path
from blink_call.modules.home.home_model import HomeModel
from blink_call.modules.i18n import get_i18n
from blink_call.modules.setting.setting_model import SettingModel
from blink_call.modules.setting.setting_viewmodel import SettingViewModel
from blink_call.utils.debug_overlay import draw_debug


audio_logger = logging.getLogger("blink_call.audio")


class HomeViewModel(QObject):
    frame_ready = Signal(QImage)
    show_camera_status = Signal(str)
    local_service_status = Signal(bool)
    blink_progress_updated = Signal(dict)
    blink_call_alert_visibility = Signal(bool)
    home_hint = Signal(dict)
    recording_state_changed = Signal(dict)

    debug_mode_state = Signal(bool)
    show_debug_msg = Signal(str)
    clear_debug_msg = Signal()

    def __init__(self, model: HomeModel):
        super().__init__()
        self.model = model

        self.setting_model = SettingModel()
        self.setting_vm = SettingViewModel(self.setting_model)
        self.model_files_manager = ModelFilesManager()
        self.setting_vm.save_setting.connect(self.on_page_enter)
        self.setting_vm.start_local_service.connect(self.on_start_service)
        self.setting_vm.start_recording_requested.connect(self.start_recording)

        self.infer_worker = InferenceWorker(self.model)
        self.infer_worker.result_ready.connect(self.on_infer_result)
        self.infer_worker.show_debug_msg.connect(self.on_infer_debug)
        self.infer_worker.eye_region_status.connect(self.on_eye_region_status)

        self.timer = QTimer(self)
        self.timer.setInterval(20)
        self.timer.timeout.connect(self.on_update_frame)

        self.call_sound_effect = QSoundEffect(self)
        self.call_sound_effect.setLoopCount(int(QSoundEffect.Loop.Infinite.value))
        self.stage_prompt_sound_player = RecoveringSoundEffect(
            get_resource_path("assets", "audio", "prompt.wav"),
            self,
        )
        self.stage_prompt_sound_player.diagnostic.connect(self.show_debug_msg.emit)
        self.call_sound_stop_timer = QTimer(self)
        self.call_sound_stop_timer.setSingleShot(True)
        self.call_sound_stop_timer.timeout.connect(self.stop_call_audio)

        self._initialize_vars()

    def _initialize_vars(self):
        self.debug_mode = bool(self.setting_vm.get_config("debug_mode"))
        self.latest_infer_result = None

        self.stat_fps_interval = 10.0
        self.ui_fps_window_start = time.perf_counter()
        self.ui_fps_counter = 0
        self.is_call_audio_playing = False
        self.setting_popup = False
        self.last_local_camera_state = None
        self.camera_frame_available = False

        self.is_recording_mode = False
        self.recording_output_dir = None
        self.recording_session_started_at = 0.0
        self.recording_segment_started_at = 0.0
        self.recording_total_seconds = max(0, int(self.setting_vm.get_config("recording.max_duration_min")) * 60)
        self.recording_target_fps = 30.0

    def emit_show_camera_status(self, key, **params):
        text = get_i18n(self.setting_vm.get_config("ui.language"))[key]
        self.show_camera_status.emit(text.format(**params))

    def on_page_enter(self):
        self._initialize_vars()
        self.stop_call_audio()
        self.stage_prompt_sound_player.stop()
        self.close_recording_writer()
        self.blink_progress_updated.emit(
            {
                "visibility": self.setting_vm.get_config("blink_call.enabled")
                and self.setting_vm.get_config("blink_call.show_home_progress_bar"),
                "progress_ratio": 0.0,
                "pattern": self.setting_vm.get_config("blink_call.pattern"),
            }
        )

        self.local_service_status.emit(False)
        self.home_hint.emit({"visible": False, "text": ""})
        self.recording_state_changed.emit({"active": False, "elapsed_s": 0, "total_s": 0})
        self.clear_debug_msg.emit()
        self.debug_mode_state.emit(self.debug_mode)

        self.stop_infer_worker()
        self.start_local_camera()

    def start_local_camera(self):
        if self.setting_model.get_config("camera.mode") == "remote":
            remote_ip = self.setting_vm.get_config("camera.remote.ip")
            remote_port = self.setting_vm.get_config("camera.remote.port")
            ok = self.model.start_remote_capture(remote_ip, remote_port)
            self.timer.start() if ok else self.timer.stop()
            self.start_infer_worker() if ok else self.stop_infer_worker()
            if not ok:
                self.emit_show_camera_status("unknown_error")

        else:
            local_camera_id = self.setting_vm.get_config("camera.local_camera_id")
            fallback_enabled = bool(self.setting_vm.get_config("camera.fallback.enabled"))
            fallback_camera_id = self.setting_vm.get_config("camera.fallback.camera_id")
            ok = self.model.start_local_capture(
                local_camera_id,
                fallback_camera_id=fallback_camera_id,
                fallback_enabled=fallback_enabled,
            )

            self.timer.start() if ok else self.timer.stop()
            self.start_infer_worker() if ok else self.stop_infer_worker()
            if not ok:
                self.emit_show_camera_status("local_invalid_camera")

    def on_update_frame(self):
        _mode, frame, status_code = self.model.read_frame()
        if frame is None:
            if self.camera_frame_available:
                self.camera_frame_available = False
                self.home_hint.emit({"visible": False, "text": ""})

            if _mode == "local":
                camera_status = self.model.get_camera_status() or {}
                state = camera_status.get("state")
                previous_state = self.last_local_camera_state
                self.last_local_camera_state = state
                if state == previous_state:
                    return
                if state in {"starting", "degraded", "reconnecting"}:
                    self.emit_show_camera_status("local_camera_reconnecting")
                else:
                    self.emit_show_camera_status("local_invalid_camera")
            elif _mode == "remote":
                self.emit_show_camera_status("remote_error", status_code=status_code)
            else:
                self.emit_show_camera_status("unknown_error")
            return

        self.camera_frame_available = True
        self.last_local_camera_state = "running" if _mode == "local" else None

        if self.debug_mode:
            self.ui_fps_counter += 1
            now = time.perf_counter()
            elapsed = now - self.ui_fps_window_start

            if elapsed >= self.stat_fps_interval:
                ui_fps = self.ui_fps_counter / elapsed
                self.show_debug_msg.emit(f"[UI] ui_frame_fps: {ui_fps:.2f}")

                self.ui_fps_window_start = now
                self.ui_fps_counter = 0

            if isinstance(self.latest_infer_result, dict) and not self.is_recording_mode:
                frame = draw_debug(frame, self.latest_infer_result)

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        image = QImage(rgb.data, w, h, ch * w, QImage.Format.Format_RGB888).copy()
        self.frame_ready.emit(image)

        if self.is_recording_mode:
            self.write_recording_frame(frame)

    def on_start_service(self):
        local_camera_id = self.setting_vm.get_config("local_service.camera_id", source="temp")
        service_port = self.setting_vm.get_config("local_service.port", source="temp")
        ok, ip, port = self.model.start_local_camera_service(local_camera_id, service_port)

        self.timer.stop()
        self.stop_infer_worker()
        self.stop_call_audio()
        self.local_service_status.emit(True)
        self.debug_mode_state.emit(False)

        if ok:
            self.emit_show_camera_status("service_started_success", ip=ip, port=port)
        else:
            self.emit_show_camera_status("service_started_failed")

    def on_infer_result(self, result):
        self.latest_infer_result = result

        self.blink_progress_updated.emit(
            {
                "visibility": self.setting_vm.get_config("blink_call.enabled")
                and self.setting_vm.get_config("blink_call.show_home_progress_bar"),
                "progress_ratio": float(result.get("blink_progress_ratio", 0.0)),
                "pattern": self.setting_vm.get_config("blink_call.pattern"),
            }
        )
        if bool(result.get("blinck_call_flag")):
            self.start_or_reset_call_audio()
        elif bool(result.get("stage_sound_prompt_flag")):
            self.play_stage_prompt_sound()

    def on_infer_debug(self, text: str):
        if self.debug_mode:
            self.show_debug_msg.emit(text)

    def on_eye_region_status(self, status):
        if not self.camera_frame_available:
            return

        key = {
            "no_face": "face_not_detected_hint",
            "landmarks_error": "keypoints_invalid_hint",
            "keypoints_invalid": "keypoints_invalid_hint",
            "inference_error": "inference_error_hint",
            # Backward-compatible aliases for older detector payloads.
            "error": "keypoints_invalid_hint",
        }.get(status)
        i18n = get_i18n(self.setting_vm.get_config("ui.language"))
        self.home_hint.emit({"visible": key is not None, "text": i18n.get(key, "")})

    def on_listen_setting_popup(self, is_open: bool):
        self.setting_popup = is_open
        if is_open:
            self.stage_prompt_sound_player.stop()

    def start_infer_worker(self):
        if not bool(self.setting_vm.get_config("blink_call.enabled")) or self.is_recording_mode:
            return

        if not self.model_files_manager.all_model_files_exists():
            i18n = get_i18n(self.setting_vm.get_config("ui.language"))
            self.home_hint.emit({"visible": True, "text": i18n["model_files_missing_hint"]})
            return

        if not self.infer_worker.isRunning():
            self.infer_worker.initialize_vars(self.setting_vm.get_config("blink_call"))
            self.infer_worker.start()

    def stop_infer_worker(self):
        self.infer_worker.stop()
        if self.infer_worker.isRunning():
            self.infer_worker.wait()

    def start_or_reset_call_audio(self):
        if (
            self.setting_popup
            or not bool(self.setting_vm.get_config("blink_call.enabled"))
            or not bool(self.setting_vm.get_config("blink_call.audio.enabled"))
        ):
            return

        file_name = self.setting_vm.get_config("blink_call.audio.file")
        if not isinstance(file_name, str) or not file_name.strip():
            return
        audio_path = Path("assets") / "audio" / file_name

        volume = int(self.setting_vm.get_config("blink_call.audio.volume"))
        volume = max(0, min(100, volume))
        self.call_sound_effect.setVolume(float(volume) / 100.0)

        source = QUrl.fromLocalFile(str(audio_path.resolve()))
        source_changed = self.call_sound_effect.source() != source
        if source_changed:
            self.call_sound_effect.setSource(source)

        # If already playing the same source, only reset countdown; do not replay/stack.
        if not self.is_call_audio_playing or source_changed:
            self.call_sound_effect.stop()
            self.call_sound_effect.play()
            self.is_call_audio_playing = True
            self.blink_call_alert_visibility.emit(True)

        duration_s = int(self.setting_vm.get_config("blink_call.audio.play_duration_s"))
        if duration_s > 0:
            self.call_sound_stop_timer.start(duration_s * 1000)
        else:
            self.call_sound_stop_timer.stop()

    def stop_call_audio(self):
        self.call_sound_stop_timer.stop()
        self.call_sound_effect.stop()
        if self.is_call_audio_playing:
            self.is_call_audio_playing = False
            self.blink_call_alert_visibility.emit(False)

    def play_stage_prompt_sound(self):
        if self.setting_popup or not bool(self.setting_vm.get_config("blink_call.enabled")):
            return

        volume = int(self.setting_vm.get_config("blink_call.audio.volume"))
        volume = max(0, min(100, volume))
        self.stage_prompt_sound_player.set_volume(float(volume) / 100.0)
        audio_logger.info("stage_prompt_requested")
        self.stage_prompt_sound_player.play()

    def start_recording(self):
        self.is_recording_mode = True

        self.blink_progress_updated.emit(
            {
                "visibility": False,
                "progress_ratio": 0.0,
                "pattern": self.setting_vm.get_config("blink_call.pattern"),
            }
        )

        self.stop_infer_worker()
        self.start_local_camera()

        folder_name = get_i18n(self.setting_vm.get_config("ui.language"))["blink_call_data_folder"]
        root_dir = self.setting_vm.get_config("recording.local_dir")
        output_dir = Path(root_dir) / folder_name
        output_dir.mkdir(parents=True, exist_ok=True)
        self.recording_output_dir = output_dir

        self.recording_session_started_at = time.perf_counter()
        self.recording_segment_started_at = 0.0
        self.recording_total_seconds = max(0, int(self.setting_vm.get_config("recording.max_duration_min")) * 60)
        self.recording_state_changed.emit({"active": True, "elapsed_s": 0, "total_s": self.recording_total_seconds})

    def stop_recording(self):
        self.is_recording_mode = False
        self.recording_state_changed.emit({"active": False, "elapsed_s": 0, "total_s": 0})

        self.close_recording_writer()
        self.on_page_enter()

    def open_recording_writer(self, frame):
        h, w = frame.shape[:2]
        file_name = f"{datetime.now().strftime('%Y_%m_%d_%H_%M_%S')}.mp4"
        file_path = self.recording_output_dir / file_name
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(str(file_path), fourcc, self.recording_target_fps, (w, h))
        if not writer.isOpened():
            self.show_debug_msg.emit(f"[Recording] failed to open writer: {file_path}")
            return

        self.recording_writer = writer
        self.recording_segment_started_at = time.perf_counter()

    def close_recording_writer(self):
        if hasattr(self, "recording_writer") and self.recording_writer is not None:
            self.recording_writer.release()
        self.recording_writer = None

    def write_recording_frame(self, frame):
        now = time.perf_counter()

        if now - self.recording_segment_started_at >= 60.0:
            self.close_recording_writer()

        if self.recording_writer is None:
            self.open_recording_writer(frame)

        if self.recording_writer is None:
            return

        self.recording_writer.write(frame)

        elapsed_s = max(0, int(now - self.recording_session_started_at))
        self.recording_state_changed.emit(
            {"active": True, "elapsed_s": elapsed_s, "total_s": self.recording_total_seconds}
        )

        if elapsed_s >= self.recording_total_seconds:
            self.stop_recording()

    def stop_all(self):
        self.timer.stop()
        self.stop_infer_worker()
        self.stop_call_audio()
        self.stage_prompt_sound_player.stop()
        self.close_recording_writer()
        self.model.stop_active_sources()
