import logging
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, QUrl, Signal
from PySide6.QtMultimedia import QMediaDevices, QSoundEffect


audio_logger = logging.getLogger("blink_call.audio")


class RecoveringSoundEffect(QObject):
    """Play a short sound effect and recover from transient backend failures."""

    diagnostic = Signal(str)

    def __init__(
        self,
        source_path: Path,
        parent=None,
        retry_delays_ms=(100, 200, 200),
        loading_timeout_ms=500,
        start_timeout_ms=150,
        _effect_factory=None,
        _scheduler=None,
        _media_devices=None,
        _default_audio_output=None,
    ):
        super().__init__(parent)
        self.source_path = Path(source_path).resolve()
        self.source_url = QUrl.fromLocalFile(str(self.source_path))
        self.retry_delays_ms = tuple(max(0, int(delay)) for delay in retry_delays_ms)
        self.loading_timeout_ms = max(1, int(loading_timeout_ms))
        self.start_timeout_ms = max(1, int(start_timeout_ms))
        self._effect_factory = _effect_factory or QSoundEffect
        self._scheduler = _scheduler or QTimer.singleShot
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

        if _media_devices is False:
            self._media_devices = None
        else:
            self._media_devices = _media_devices or QMediaDevices(self)
            self._media_devices.audioOutputsChanged.connect(self._on_audio_outputs_changed)

        self._create_effect("initial")

    def set_volume(self, volume: float):
        self._volume = max(0.0, min(1.0, float(volume)))
        if self._effect is not None:
            self._effect.setVolume(self._volume)

    def play(self):
        if self._pending_play:
            self._emit_diagnostic(f"play_coalesced; request={self._request_id}")
            return

        self._request_id += 1
        request_id = self._request_id
        self._pending_play = True
        self._awaiting_start = False
        self._retry_attempt = 0
        self._retry_scheduled = False
        self._loading_wait_key = None

        if not self.source_path.is_file():
            self._pending_play = False
            audio_logger.warning("stage_prompt_failed reason=source_missing source=%s", self.source_path)
            self._emit_diagnostic(f"play_skipped; reason=source_missing; source={self.source_path}")
            return

        self._attempt_play(request_id)

    def stop(self):
        self._request_id += 1
        self._pending_play = False
        self._awaiting_start = False
        self._retry_scheduled = False
        self._loading_wait_key = None
        if self._effect is not None:
            self._effect.stop()

    def _create_effect(self, reason: str):
        previous_effect = self._effect
        if previous_effect is not None:
            previous_effect.stop()
            if hasattr(previous_effect, "deleteLater"):
                previous_effect.deleteLater()

        self._generation += 1
        generation = self._generation
        effect = self._effect_factory(self)
        self._effect = effect
        effect.setLoopCount(1)
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
        audio_logger.info("stage_prompt_started request=%s generation=%s", request_id, self._generation)
        self._emit_diagnostic(f"play_started; request={request_id}; generation={self._generation}")

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
                "stage_prompt_failed request=%s reason=%s attempts=%s source=%s",
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
        if self._pending_play:
            self._attempt_play(self._request_id)

    def _on_playing_changed(self, effect, generation: int):
        if effect is not self._effect or generation != self._generation:
            return
        if effect.isPlaying() and self._pending_play:
            self._mark_started(self._request_id)

    def _on_audio_outputs_changed(self):
        had_pending_play = self._pending_play
        request_id = self._request_id
        self._retry_attempt = 0
        self._retry_scheduled = False
        self._loading_wait_key = None
        self._awaiting_start = False
        self._create_effect("audio_outputs_changed")
        if had_pending_play:
            self._attempt_play(request_id)

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
        self.diagnostic.emit(f"[StagePromptAudio] {text}")
