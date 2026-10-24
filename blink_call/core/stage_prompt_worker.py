"""Short-lived Windows prompt worker. Keep this module independent of Qt."""

import io
import math
import os
import sys
import threading
import wave
from array import array
from pathlib import Path

STAGE_PROMPT_ARGUMENT = "--play-stage-prompt"
NATIVE_PLAYBACK_TIMEOUT_EXIT_CODE = 3


def _wav_at_volume(source_path: Path, volume: float):
    with wave.open(str(source_path), "rb") as source:
        if source.getcomptype() != "NONE" or source.getsampwidth() != 2:
            raise ValueError("The stage prompt must be an uncompressed 16-bit PCM WAV file.")
        params = source.getparams()
        duration_s = source.getnframes() / source.getframerate()
        frames = source.readframes(source.getnframes())

    # Adjust only this cue's PCM samples, never the system or another app's volume.
    if volume < 1.0:
        samples = array("h", frames)
        if sys.byteorder != "little":
            samples.byteswap()
        samples = array("h", (int(sample * volume) for sample in samples))
        if sys.byteorder != "little":
            samples.byteswap()
        frames = samples.tobytes()

    output = io.BytesIO()
    with wave.open(output, "wb") as destination:
        destination.setparams(params)
        destination.writeframes(frames)
    return output.getvalue(), duration_s


def run_stage_prompt(arguments) -> int:
    """Synchronously play one cue, then exit and release all worker resources."""
    try:
        if sys.platform != "win32":
            raise RuntimeError("The native stage prompt worker is available only on Windows.")
        if len(arguments) != 2:
            raise ValueError("Expected a WAV path and a volume between 0 and 1.")
        source_path = Path(arguments[0]).resolve()
        volume = float(arguments[1])
        if not math.isfinite(volume) or not 0.0 <= volume <= 1.0:
            raise ValueError("Volume must be between 0 and 1.")
        if volume == 0:
            return 0

        import winsound

        wav_data, duration_s = _wav_at_volume(source_path, volume)
        # Also bound the worker's lifetime if the GUI crashes or its event loop
        # stalls. PlaySound releases the GIL while the Windows call is running.
        watchdog = threading.Timer(
            max(3.0, duration_s + 2.0),
            os._exit,
            args=(NATIVE_PLAYBACK_TIMEOUT_EXIT_CODE,),
        )
        watchdog.daemon = True
        watchdog.start()
        try:
            # No SND_ASYNC: return only after playback completes, before exiting.
            winsound.PlaySound(wav_data, winsound.SND_MEMORY | winsound.SND_NODEFAULT)
        finally:
            watchdog.cancel()
        return 0
    except Exception as exc:
        if sys.stderr is not None:
            print(f"stage_prompt_failed: {exc}", file=sys.stderr, flush=True)
        return 1
