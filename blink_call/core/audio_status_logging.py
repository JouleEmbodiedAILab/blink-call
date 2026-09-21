"""Dedicated, opt-in logging for audio playback diagnostics.

This log is deliberately separate from the general debug log.  Audio backends
often fail without surfacing an error to the UI, so a compact record of device
changes and QSoundEffect state is useful when investigating a missing alert.
"""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


AUDIO_STATUS_LOGGER_NAME = "blink_call.audio_status"
AUDIO_STATUS_LOG_FILENAME = "audio_status.log"
_HANDLER_PATH_ATTR = "_blink_call_audio_status_log_path"


def configure_audio_status_logging(
    log_dir,
    enabled: bool,
    max_bytes: int = 2 * 1024 * 1024,
    backup_count: int = 3,
):
    """Enable or disable the rolling audio-status log.

    Failures to create the diagnostic log are intentionally ignored so an
    unavailable log folder can never stop an assistive call from playing.
    """
    logger = logging.getLogger(AUDIO_STATUS_LOGGER_NAME)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    if not enabled:
        _remove_managed_handlers(logger)
        return None

    log_path = Path(log_dir) / AUDIO_STATUS_LOG_FILENAME
    resolved_path = log_path.resolve()
    for handler in logger.handlers:
        if getattr(handler, _HANDLER_PATH_ATTR, None) == resolved_path:
            return log_path

    _remove_managed_handlers(logger)
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            log_path,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
    except OSError:
        return None

    setattr(handler, _HANDLER_PATH_ATTR, resolved_path)
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    logger.addHandler(handler)
    logger.info("event=logging_started path=%s", log_path)
    return log_path


def log_audio_status(component: str, event: str, **details):
    """Record one concise audio diagnostic event when the logger is enabled."""
    if not details:
        logging.getLogger(AUDIO_STATUS_LOGGER_NAME).info(
            "component=%s event=%s", component, event
        )
        return

    detail_text = " ".join(
        f"{key}={_clean_value(value)}" for key, value in sorted(details.items())
    )
    logging.getLogger(AUDIO_STATUS_LOGGER_NAME).info(
        "component=%s event=%s %s", component, event, detail_text
    )


def _remove_managed_handlers(logger):
    for handler in tuple(logger.handlers):
        if not hasattr(handler, _HANDLER_PATH_ATTR):
            continue
        logger.removeHandler(handler)
        handler.close()


def _clean_value(value) -> str:
    return str(value).replace("\r", "\\r").replace("\n", "\\n")
