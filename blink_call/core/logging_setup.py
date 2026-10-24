import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


def configure_app_logging(log_dir, max_bytes=5 * 1024 * 1024, backup_count=3):
    """Configure an always-on rolling log for lifecycle and recovery events."""
    log_dir = Path(log_dir)
    log_path = log_dir / "blink_call.log"

    app_logger = logging.getLogger("blink_call")
    app_logger.setLevel(logging.INFO)
    app_logger.propagate = False

    resolved_path = log_path.resolve()
    for existing_handler in app_logger.handlers:
        if getattr(existing_handler, "_blink_call_log_path", None) == resolved_path:
            return log_path

    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            log_path,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
    except OSError:
        # A logging-path failure must never prevent the assistive application
        # from starting. Camera status is still surfaced in the UI.
        return None
    handler._blink_call_log_path = resolved_path
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s [%(threadName)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    app_logger.addHandler(handler)
    app_logger.info("logging_started path=%s", log_path)
    return log_path
