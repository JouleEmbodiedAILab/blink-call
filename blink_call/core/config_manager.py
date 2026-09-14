from copy import deepcopy
from pathlib import Path

from blink_call.utils.helper import Helper

LOCAL_CONFIG_PATH = "configs/local_config.yaml"


class ConfigManager:
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
            "startup": {"enabled": False},
            "recording": {"max_duration_min": 1, "local_dir": default_log_dir},
            "blink_call": {
                "enabled": True,
                "show_home_progress_bar": True,
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

        path = Path(LOCAL_CONFIG_PATH)
        if path.exists():
            local_config = Helper.read_yaml(path)
            return Helper.deep_merge_dict(default_config, local_config)

        cls.save_local_config(default_config)
        return default_config

    @classmethod
    def save_local_config(cls, local_config):
        Helper.write_yaml(Path(LOCAL_CONFIG_PATH), local_config)

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
