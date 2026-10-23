import logging
import math
import time
import wave
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, QUrl, Signal
from PySide6.QtMultimedia import QMediaDevices, QSoundEffect

from blink_call.core.audio_status_logging import log_audio_status


audio_logger = logging.getLogger("blink_call.audio")


class RecoveringSoundEffect(QObject):
    """Play a sound effect and recover from transient backend failures."""

    diagnostic = Signal(str)

    def __init__(
        self,
        source_path: Path,
        parent=None,
        retry_delays_ms=(100, 200, 200),
        loading_timeout_ms=2000,
        start_timeout_ms=150,
        _effect_factory=None,
        _scheduler=None,
        _media_devices=None,
        _default_audio_output=None,
        _clock=None,
        *,
        loop_count=1,
        component="stage_prompt",
    ):
        super().__init__(parent)
        self.source_path = Path(source_path).resolve()
        self.source_url = QUrl.fromLocalFile(str(self.source_path))
        self.retry_delays_ms = tuple(max(0, int(delay)) for delay in retry_delays_ms)
        self.loading_timeout_ms = max(1, int(loading_timeout_ms))
        self.start_timeout_ms = max(1, int(start_timeout_ms))
        self._loop_count = int(loop_count)
        self._continuous = self._loop_count == int(QSoundEffect.Loop.Infinite.value)
        self._component = component
        self._effect_factory = _effect_factory or QSoundEffect
        self._scheduler = _scheduler or QTimer.singleShot
        self._clock = _clock or time.monotonic
        self._default_audio_output = _default_audio_output or QMediaDevices.defaultAudioOutput

        self._effect = None
        self._volume = 1.0
        self._generation = 0
        self._request_id = 0
        self._pending_play = False
        self._awaiting_start = False
        self._retry_attempt = 0
        self._retry_scheduled = False
        self._loading_wait_key = None
        self._play_requested = False
        self._source_duration_ms = None
        self._playback_deadline = None

        self._monitor_timer = QTimer(self)
        self._monitor_timer.setInterval(2000)
        self._monitor_timer.timeout.connect(self._monitor_playback)

        if _media_devices is False:
            self._media_devices = None
        else:
            self._media_devices = _media_devices or QMediaDevices(self)
            self._media_devices.audioOutputsChanged.connect(self._on_audio_outputs_changed)

        self._create_effect("initial")

    def set_source(self, source_path: Path):
        source_path = Path(source_path).resolve()
        if source_path == self.source_path:
            return
        self.stop()
        self.source_path = source_path
        self.source_url = QUrl.fromLocalFile(str(source_path))
        self._create_effect("source_changed")

    def set_volume(self, volume: float):
        self._volume = max(0.0, min(1.0, float(volume)))
        if self._effect is not None:
            self._effect.setVolume(self._volume)
        self._emit_diagnostic(f"volume_updated; volume={self._volume:.2f}")

    def play(self):
        # A queued play request may run before an overdue timer after the UI
        # thread was busy. Retire a stalled sink before reusing it in that case.
        if self._playback_deadline is not None and self._clock() >= self._playback_deadline:
            self._verify_finished(self._effect, self._generation, self._request_id)

        if self._pending_play:
            self._emit_diagnostic(f"play_coalesced; request={self._request_id}")
            return

        if self._continuous and self._play_requested and self._effect.isPlaying():
            return

        self._request_id += 1
        request_id = self._request_id
        self._pending_play = True
        self._awaiting_start = False
        self._retry_attempt = 0
        self._retry_scheduled = False
        self._loading_wait_key = None
        self._play_requested = True
        self._playback_deadline = None
        self._emit_diagnostic(f"play_requested; request={request_id}")

        if not self.source_path.is_file():
            self._pending_play = False
            self._play_requested = False
            self._monitor_timer.stop()
            audio_logger.warning("%s_failed reason=source_missing source=%s", self._component, self.source_path)
            self._emit_diagnostic(f"play_skipped; reason=source_missing; source={self.source_path}")
            return

        if self._continuous:
            self._monitor_timer.start()
        self._attempt_play(request_id)

    def stop(self):
        self._emit_diagnostic(f"play_stopped; request={self._request_id}")
        self._request_id += 1
        self._play_requested = False
        self._playback_deadline = None
        self._monitor_timer.stop()
        self._pending_play = False
        self._awaiting_start = False
        self._retry_scheduled = False
        self._loading_wait_key = None
        if self._effect is not None:
            self._effect.stop()

    def _create_effect(self, reason: str):
        previous_effect = self._effect
        self._playback_deadline = None
        # Invalidate callbacks before stop(), which may emit playingChanged
        # synchronously from the old backend.
        self._generation += 1
        generation = self._generation
        self._effect = None
        if previous_effect is not None:
            previous_effect.stop()
            if hasattr(previous_effect, "deleteLater"):
                previous_effect.deleteLater()

        effect = self._effect_factory(self)
        self._effect = effect
        effect.setLoopCount(self._loop_count)
        effect.setVolume(self._volume)
        effect.statusChanged.connect(lambda effect=effect: self._on_status_changed(effect, generation))
        effect.loadedChanged.connect(lambda effect=effect: self._on_status_changed(effect, generation))
        effect.playingChanged.connect(lambda effect=effect: self._on_playing_changed(effect, generation))

        device = self._get_default_audio_output()
        if device is not None and not self._device_is_null(device):
            effect.setAudioDevice(device)

        if self.source_path.is_file():
            effect.setSource(self.source_url)

        self._emit_diagnostic(
            f"effect_created; reason={reason}; generation={generation}; "
            f"source_exists={self.source_path.is_file()}; device={self._device_description(device)}"
        )
        # Keep the basic evidence in the normal application log as well. A
        # packaged Windows GUI has no console, and detailed audio logging may
        # not have been enabled when an initial load failure occurred.
        audio_logger.info(
            "%s_backend_created reason=%s generation=%s source=%s exists=%s device=%s",
            self._component, reason, generation, self.source_path,
            self.source_path.is_file(), self._device_description(device),
        )
        if reason in ("initial", "source_changed"):
            self._log_source_format()

    def _attempt_play(self, request_id: int):
        if request_id != self._request_id or not self._pending_play or self._effect is None:
            return

        status = self._effect.status()
        if status == QSoundEffect.Status.Ready and self._effect.isLoaded():
            self._start_ready_effect(self._effect, self._generation, request_id)
            return

        if status == QSoundEffect.Status.Loading:
            self._wait_for_loading(self._effect, self._generation, request_id)
            return

        self._schedule_retry(request_id, f"status_{self._status_name(status)}")

    def _start_ready_effect(self, effect, generation: int, request_id: int):
        if not self._is_current(effect, generation, request_id) or self._awaiting_start:
            return

        self._awaiting_start = True
        if effect.isPlaying():
            effect.stop()
            self._scheduler(0, lambda: self._invoke_play(effect, generation, request_id))
        else:
            self._invoke_play(effect, generation, request_id)

    def _invoke_play(self, effect, generation: int, request_id: int):
        if not self._is_current(effect, generation, request_id):
            return

        effect.play()
        if effect.isPlaying():
            self._mark_started(request_id)
            return

        self._scheduler(
            self.start_timeout_ms,
            lambda: self._verify_started(effect, generation, request_id),
        )

    def _verify_started(self, effect, generation: int, request_id: int):
        if not self._is_current(effect, generation, request_id):
            return
        if effect.isPlaying():
            self._mark_started(request_id)
            return

        self._awaiting_start = False
        self._schedule_retry(request_id, f"start_failed_{self._status_name(effect.status())}")

    def _mark_started(self, request_id: int):
        if request_id != self._request_id or not self._pending_play:
            return
        self._pending_play = False
        self._awaiting_start = False
        self._retry_scheduled = False
        self._loading_wait_key = None
        if not self._continuous and self._source_duration_ms is not None:
            # QSoundEffect can report Ready/playing=True while its sink is
            # stalled. isPlaying() only acknowledges the play command; require
            # a finite sound to finish within its WAV duration plus drain time.
            timeout_ms = self._source_duration_ms * max(1, self._loop_count) + 500
            self._playback_deadline = self._clock() + timeout_ms / 1000.0
            effect, generation = self._effect, self._generation
            self._scheduler(timeout_ms, lambda: self._verify_finished(effect, generation, request_id))
        audio_logger.info("%s_started request=%s generation=%s", self._component, request_id, self._generation)
        self._emit_diagnostic(f"play_started; request={request_id}; generation={self._generation}")

    def _verify_finished(self, effect, generation: int, request_id: int):
        if (
            effect is not self._effect
            or generation != self._generation
            or request_id != self._request_id
            or self._continuous
            or self._pending_play
            or not self._play_requested
        ):
            return

        if not effect.isPlaying():
            self._mark_finished()
            return

        self.log_state("playback_timeout")
        audio_logger.warning(
            "%s_playback_timeout request=%s generation=%s duration_ms=%s source=%s",
            self._component, request_id, generation, self._source_duration_ms, self.source_path,
        )
        self._emit_diagnostic(f"playback_timeout; request={request_id}; generation={generation}")
        self._play_requested = False
        # The step has already passed: do not replay an outdated cue. Discard
        # the stuck sink and preload a fresh one for the next step/preview.
        self._create_effect("playback_timeout")

    def _mark_finished(self):
        self._play_requested = False
        self._playback_deadline = None
        audio_logger.info("%s_finished request=%s generation=%s", self._component, self._request_id, self._generation)
        self._emit_diagnostic(f"play_finished; request={self._request_id}; generation={self._generation}")

    def _wait_for_loading(self, effect, generation: int, request_id: int):
        wait_key = (generation, request_id)
        if self._loading_wait_key == wait_key:
            return
        self._loading_wait_key = wait_key
        self._scheduler(
            self.loading_timeout_ms,
            lambda: self._on_loading_timeout(effect, generation, request_id, wait_key),
        )

    def _on_loading_timeout(self, effect, generation: int, request_id: int, wait_key):
        if self._loading_wait_key != wait_key or not self._is_current(effect, generation, request_id):
            return
        self._loading_wait_key = None
        if effect.status() == QSoundEffect.Status.Ready and effect.isLoaded():
            self._attempt_play(request_id)
            return
        self._schedule_retry(request_id, f"load_timeout_{self._status_name(effect.status())}")

    def _schedule_retry(self, request_id: int, reason: str):
        if request_id != self._request_id or not self._pending_play or self._retry_scheduled:
            return

        if self._retry_attempt >= len(self.retry_delays_ms):
            self._pending_play = False
            self._awaiting_start = False
            self._loading_wait_key = None
            audio_logger.warning(
                "%s_failed request=%s reason=%s attempts=%s source=%s",
                self._component,
                request_id,
                reason,
                self._retry_attempt,
                self.source_path,
            )
            self._emit_diagnostic(
                f"play_failed; request={request_id}; reason={reason}; "
                f"attempts={self._retry_attempt}; source={self.source_path}"
            )
            return

        delay_ms = self.retry_delays_ms[self._retry_attempt]
        self._retry_attempt += 1
        attempt = self._retry_attempt
        self._awaiting_start = False
        self._retry_scheduled = True
        self._emit_diagnostic(
            f"retry_scheduled; request={request_id}; attempt={attempt}/{len(self.retry_delays_ms)}; "
            f"delay_ms={delay_ms}; reason={reason}"
        )
        generation = self._generation
        self._scheduler(delay_ms, lambda: self._run_retry(request_id, attempt, generation))

    def _run_retry(self, request_id: int, attempt: int, scheduled_generation: int):
        if (
            request_id != self._request_id
            or not self._pending_play
            or scheduled_generation != self._generation
        ):
            return
        self._retry_scheduled = False
        self._loading_wait_key = None
        self._create_effect(f"retry_{attempt}")
        self._attempt_play(request_id)

    def _on_status_changed(self, effect, generation: int):
        if effect is not self._effect or generation != self._generation:
            return
        self._emit_diagnostic(
            f"status_changed; generation={generation}; status={self._status_name(effect.status())}; "
            f"loaded={effect.isLoaded()}; playing={effect.isPlaying()}"
        )
        if effect.status() == QSoundEffect.Status.Error:
            audio_logger.warning(
                "%s_backend_error generation=%s source=%s device=%s",
                self._component, generation, self.source_path,
                self._device_description(self._get_default_audio_output()),
            )
        if self._pending_play:
            self._attempt_play(self._request_id)

    def _on_playing_changed(self, effect, generation: int):
        if effect is not self._effect or generation != self._generation:
            return
        self.log_state("playing_changed")
        if effect.isPlaying() and self._pending_play:
            self._mark_started(self._request_id)
        elif not effect.isPlaying() and not self._pending_play and not self._continuous and self._play_requested:
            self._mark_finished()

    def _on_audio_outputs_changed(self):
        resume_play = self._pending_play or (self._continuous and self._play_requested)
        request_id = self._request_id
        self._pending_play = resume_play
        self._play_requested = resume_play
        self._retry_attempt = 0
        self._retry_scheduled = False
        self._loading_wait_key = None
        self._awaiting_start = False
        self._create_effect("audio_outputs_changed")
        if resume_play:
            self._attempt_play(request_id)

    def _monitor_playback(self):
        if not self._continuous or not self._play_requested or self._pending_play:
            return
        if self._effect.status() == QSoundEffect.Status.Ready and self._effect.isPlaying():
            return
        # A loop can stop after its initial successful start (device removal,
        # suspend/resume, or a backend error). Recreate the sink while the
        # caller still requests an alarm; stop() cancels all further recovery.
        self._create_effect("playback_interrupted")
        self.play()

    def log_state(self, event: str):
        effect = self._effect
        audio_logger.info(
            "%s_state event=%s status=%s loaded=%s playing=%s requested=%s volume=%.2f source=%s",
            self._component, event, self._status_name(effect.status()),
            effect.isLoaded(), effect.isPlaying(), self._play_requested, self._volume, self.source_path,
        )
        log_audio_status(
            self._component,
            event,
            status=self._status_name(effect.status()),
            loaded=effect.isLoaded(),
            playing=effect.isPlaying(),
            duration_ms=self._source_duration_ms,
            loops=self._loop_count,
            source=self.source_path,
            requested=self._play_requested,
            volume=f"{self._volume:.2f}",
        )

    def _log_source_format(self):
        self._source_duration_ms = None
        try:
            with wave.open(str(self.source_path), "rb") as source:
                if source.getframerate() > 0:
                    self._source_duration_ms = math.ceil(source.getnframes() * 1000 / source.getframerate())
                audio_logger.info(
                    "%s_source_format channels=%s sample_rate=%s sample_bytes=%s frames=%s "
                    "compression=%s duration_ms=%s",
                    self._component, source.getnchannels(), source.getframerate(),
                    source.getsampwidth(), source.getnframes(), source.getcomptype(),
                    self._source_duration_ms,
                )
        except (OSError, EOFError, wave.Error) as exc:
            audio_logger.warning("%s_source_unreadable source=%s detail=%s", self._component, self.source_path, exc)

    def _is_current(self, effect, generation: int, request_id: int) -> bool:
        return (
            effect is self._effect
            and generation == self._generation
            and request_id == self._request_id
            and self._pending_play
        )

    def _get_default_audio_output(self):
        try:
            return self._default_audio_output()
        except Exception as exc:
            self._emit_diagnostic(f"default_audio_output_error; error={exc}")
            return None

    @staticmethod
    def _device_is_null(device) -> bool:
        try:
            return bool(device.isNull())
        except (AttributeError, RuntimeError):
            return False

    @staticmethod
    def _device_description(device) -> str:
        if device is None:
            return "none"
        try:
            return str(device.description() or "unnamed")
        except (AttributeError, RuntimeError):
            return "unknown"

    @staticmethod
    def _status_name(status) -> str:
        return getattr(status, "name", str(status))

    def _emit_diagnostic(self, text: str):
        log_audio_status(self._component, "state", message=text)
        self.diagnostic.emit(f"[{self._component}] {text}")
