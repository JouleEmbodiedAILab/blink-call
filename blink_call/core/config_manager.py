from copy import deepcopy
from pathlib import Path
import sys

from PySide6.QtCore import QStandardPaths

from blink_call.utils.helper import Helper

LEGACY_CONFIG_PATH = Path("configs/local_config.yaml")


class ConfigManager:
    @classmethod
    def _local_config_path(cls) -> Path:
        if sys.platform != "win32":
            return LEGACY_CONFIG_PATH
        app_data_dir = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation)
        if not app_data_dir:
            app_data_dir = QStandardPaths.writableLocation(QStandardPaths.TempLocation)
        return Path(app_data_dir) / "blink_call" / "local_config.yaml"

    @classmethod
    def get_default_config(cls):
        default_log_dir = str(Path.home() / "Desktop")
        _default_config = {
            "ui": {"language": "zh", "theme": "light"},
            "camera": {
                "mode": "local",
                "local_camera_id": 0,
                "fallback": {"enabled": False, "camera_id": 1},
                "remote": {"ip": "0.0.0.0", "port": 17925},
            },
            "local_service": {"camera_id": 0, "port": 17925},
            "startup": {"enabled": True, "default_policy_version": 1},
            "recording": {"max_duration_min": 1, "local_dir": default_log_dir},
            "blink_call": {
                "enabled": True,
                "show_home_progress_bar": True,
                "abnormal_alert": {
                    "enabled": False,
                    "camera_missing_after_s": 300,
                    "face_missing_after_s": 300,
                },
                "audio": {
                    "enabled": True,
                    "file": "ring_01.wav",
                    "volume": 100,
                    "play_duration_s": 60,
                },
                "pattern": [
                    {"state": "open", "duration_s": 1.5, "sound_prompt": False},
                    {"state": "closed", "duration_s": 1.0, "sound_prompt": True},
                    {"state": "open", "duration_s": 1.0, "sound_prompt": True},
                    {"state": "closed", "duration_s": 1.5, "sound_prompt": True},
                ],
                "eye_region_detection_algorithm": {},
                "eye_state_classification_algorithm": {
                    "open_confidence_thresh": 0.5,
                    "closed_confidence_thresh": 0.5,
                },
            },
            "debug_mode": False,
            "debug_log": {"save_to_local": False, "local_dir": default_log_dir},
        }

        return _default_config

    @classmethod
    def get_local_config(cls):
        default_config = cls.get_default_config()

        path = cls._local_config_path()
        source_path = path
        if sys.platform == "win32" and not path.exists():
            # Older builds wrote next to BlinkCall.exe; a shortcut may start
            # the new build with a different working directory.
            executable_dir = Path(sys.argv[0]).resolve().parent if sys.argv else Path.cwd()
            for legacy_path in (executable_dir / LEGACY_CONFIG_PATH, LEGACY_CONFIG_PATH):
                if legacy_path.exists():
                    source_path = legacy_path
                    break
        if source_path.exists():
            local_config = Helper.read_yaml(source_path)
            if not isinstance(local_config, dict):
                local_config = {}
            startup = local_config.get("startup")
            if not isinstance(startup, dict):
                startup = {}
                local_config["startup"] = startup
            try:
                policy_version = int(startup.get("default_policy_version", 0))
            except (TypeError, ValueError):
                policy_version = 0
            if policy_version < 1:
                startup["enabled"] = True
                startup["default_policy_version"] = 1
            if source_path != path or policy_version < 1:
                cls.save_local_config(local_config)
            return Helper.deep_merge_dict(default_config, local_config)

        cls.save_local_config(default_config)
        return default_config

    @classmethod
    def save_local_config(cls, local_config):
        Helper.write_yaml(cls._local_config_path(), local_config)

    @classmethod
    def update_local_config(cls, patch):
        current = cls.get_local_config()
        merged = Helper.deep_merge_dict(current, patch or {})
        cls.save_local_config(merged)
        return merged

    @classmethod
    def reset_local_config_to_default(cls):
        default_config = deepcopy(cls.get_default_config())
        cls.save_local_config(default_config)
        return default_config
