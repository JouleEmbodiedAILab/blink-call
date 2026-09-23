from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtMultimedia import QSoundEffect
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
)

from blink_call.core.model_files_manager import ModelFilesManager
from blink_call.modules.i18n import get_i18n
from blink_call.modules.setting.bindings import ConfigBinder
from blink_call.widget import InteractionBlockOverlay, NoWheelSpinBox


class BlinkCallController:
    def __init__(self, setting_view):
        self.setting_view = setting_view
        self.vm = setting_view.vm
        self.page = setting_view.blink_call_page

        self.block_overlay = InteractionBlockOverlay(self.setting_view)
        self.block_overlay.setObjectName("settingModelFilesBlockOverlay")
        self.block_overlay.hide()

        self.sequence_rows = []
        self.audio_file_values = [f"ring_{i:02d}.wav" for i in range(1, 11)]
        self.audio_duration_values = [10, 30, 60, 300, 600, 1800, 3600, -1]
        self.abnormal_alert_duration_values = [10, 30, 60, 300, 600, 1800, 3600]
        self.preview_sound = QSoundEffect(setting_view)
        self.model_files_manager = ModelFilesManager()

        self.bind()

    def bind(self):
        ConfigBinder.bind_combo(self.vm, self.page.audio_file_combo, "blink_call.audio.file")
        ConfigBinder.bind_combo(self.vm, self.page.audio_duration_combo, "blink_call.audio.play_duration_s")
        ConfigBinder.bind_slider(self.vm, self.page.audio_volume_slider, "blink_call.audio.volume")

        blink_call_group = QButtonGroup()
        blink_call_group.addButton(self.page.enabled_radio)
        blink_call_group.addButton(self.page.disabled_radio)
        self.page.enabled_radio.setProperty("tag_value", True)
        self.page.disabled_radio.setProperty("tag_value", False)
        ConfigBinder.bind_radio_group(self.vm, blink_call_group, "blink_call.enabled", self.update_sequence_visibility)
        self.blink_call_group = blink_call_group

        abnormal_alert_group = QButtonGroup()
        abnormal_alert_group.addButton(self.page.abnormal_alert_on_radio)
        abnormal_alert_group.addButton(self.page.abnormal_alert_off_radio)
        self.page.abnormal_alert_on_radio.setProperty("tag_value", True)
        self.page.abnormal_alert_off_radio.setProperty("tag_value", False)
        ConfigBinder.bind_radio_group(
            self.vm,
            abnormal_alert_group,
            "blink_call.abnormal_alert.enabled",
            self.update_abnormal_alert_visibility,
        )
        self.abnormal_alert_group = abnormal_alert_group

        ConfigBinder.bind_combo(
            self.vm,
            self.page.camera_missing_duration_combo,
            "blink_call.abnormal_alert.camera_missing_after_s",
        )
        ConfigBinder.bind_combo(
            self.vm,
            self.page.face_missing_duration_combo,
            "blink_call.abnormal_alert.face_missing_after_s",
        )

        blink_call_progress_group = QButtonGroup()
        blink_call_progress_group.addButton(self.page.progress_show_radio)
        blink_call_progress_group.addButton(self.page.progress_hide_radio)
        self.page.progress_show_radio.setProperty("tag_value", True)
        self.page.progress_hide_radio.setProperty("tag_value", False)
        ConfigBinder.bind_radio_group(self.vm, blink_call_progress_group, "blink_call.show_home_progress_bar")
        self.blink_call_progress_group = blink_call_progress_group

        blink_call_audio_group = QButtonGroup()
        blink_call_audio_group.addButton(self.page.audio_on_radio)
        blink_call_audio_group.addButton(self.page.audio_off_radio)
        self.page.audio_on_radio.setProperty("tag_value", True)
        self.page.audio_off_radio.setProperty("tag_value", False)
        ConfigBinder.bind_radio_group(
            self.vm,
            blink_call_audio_group,
            "blink_call.audio.enabled",
            self.update_audio_visibility,
        )
        self.blink_call_audio_group = blink_call_audio_group

        self.page.add_step_btn.clicked.connect(self.on_add_step)
        self.page.audio_preview_btn.clicked.connect(self.on_preview_audio)
        self.page.audio_volume_slider.valueChanged.connect(self.update_audio_volume_text)
        self.page.model_btn.clicked.connect(lambda: self.model_files_manager.start_download_or_update(timeout_s=10.0))

        for idx, file_name in enumerate(self.audio_file_values, start=1):
            self.page.audio_file_combo.addItem(f"Audio {idx}", file_name)
        for duration_s in self.audio_duration_values:
            self.page.audio_duration_combo.addItem(str(duration_s), duration_s)
        for combo in (
            self.page.camera_missing_duration_combo,
            self.page.face_missing_duration_combo,
        ):
            combo.blockSignals(True)
            for duration_s in self.abnormal_alert_duration_values:
                combo.addItem(str(duration_s), duration_s)
            combo.blockSignals(False)

        self.model_files_manager.status_changed.connect(self.on_model_files_status_changed)
        self.model_files_manager.download_started.connect(self.on_model_files_download_started)
        self.model_files_manager.download_progress.connect(self.on_model_files_download_progress)
        self.model_files_manager.download_finished.connect(self.on_model_files_download_finished)

    def refresh_from_local_config(self):
        if bool(self.vm.get_config("blink_call.enabled")):
            self.page.enabled_radio.setChecked(True)
        else:
            self.page.disabled_radio.setChecked(True)

        if bool(self.vm.get_config("blink_call.show_home_progress_bar")):
            self.page.progress_show_radio.setChecked(True)
        else:
            self.page.progress_hide_radio.setChecked(True)

        if bool(self.vm.get_config("blink_call.audio.enabled")):
            self.page.audio_on_radio.setChecked(True)
        else:
            self.page.audio_off_radio.setChecked(True)

        if bool(self.vm.get_config("blink_call.abnormal_alert.enabled")):
            self.page.abnormal_alert_on_radio.setChecked(True)
        else:
            self.page.abnormal_alert_off_radio.setChecked(True)

        for combo, path in (
            (
                self.page.camera_missing_duration_combo,
                "blink_call.abnormal_alert.camera_missing_after_s",
            ),
            (
                self.page.face_missing_duration_combo,
                "blink_call.abnormal_alert.face_missing_after_s",
            ),
        ):
            index = combo.findData(self.vm.get_config(path))
            combo.blockSignals(True)
            combo.setCurrentIndex(index if index >= 0 else combo.findData(300))
            combo.blockSignals(False)

        audio_file_idx = self.page.audio_file_combo.findData(self.vm.get_config("blink_call.audio.file"))
        self.page.audio_file_combo.blockSignals(True)
        self.page.audio_file_combo.setCurrentIndex(0 if audio_file_idx < 0 else audio_file_idx)
        self.page.audio_file_combo.blockSignals(False)

        audio_duration_idx = self.page.audio_duration_combo.findData(
            self.vm.get_config("blink_call.audio.play_duration_s")
        )
        self.page.audio_duration_combo.blockSignals(True)
        self.page.audio_duration_combo.setCurrentIndex(0 if audio_duration_idx < 0 else audio_duration_idx)
        self.page.audio_duration_combo.blockSignals(False)

        audio_volume = int(self.vm.get_config("blink_call.audio.volume"))
        self.page.audio_volume_slider.blockSignals(True)
        self.page.audio_volume_slider.setValue(max(0, min(100, audio_volume)))
        self.page.audio_volume_slider.blockSignals(False)
        self.update_audio_volume_text(self.page.audio_volume_slider.value())

        for row in self.sequence_rows:
            row["widget"].deleteLater()
        self.sequence_rows.clear()

        pattern = self.normalize_pattern(self.vm.get_config("blink_call.pattern"))
        for item in pattern:
            self._add_sequence_row(item["state"], float(item["duration_s"]), bool(item["sound_prompt"]))

        self.update_sequence_visibility()
        self.model_files_manager.start_check_status(timeout_s=10.0)

        i18n = get_i18n(self.vm.get_config("ui.language"))

        self.page.switch_label.setText(i18n["enable_blink_call"])
        self.page.enabled_radio.setText(i18n["on"])
        self.page.disabled_radio.setText(i18n["off"])
        self.page.progress_label.setText(i18n["show_top_progress_bar_on_home_page"])
        self.page.progress_show_radio.setText(i18n["show"])
        self.page.progress_hide_radio.setText(i18n["hide"])
        self.page.sequence_label.setText(i18n["blink_sequence"])
        self.page.add_step_btn.setText(i18n["add_step"])
        self.page.audio_switch_label.setText(i18n["play_call_audio"])
        self.page.audio_on_radio.setText(i18n["on"])
        self.page.audio_off_radio.setText(i18n["off"])
        self.page.audio_file_label.setText(i18n["call_audio_file"])
        self.page.audio_preview_btn.setText(i18n["preview"])
        self.page.audio_volume_label.setText(i18n["audio_volume"])
        self.page.audio_duration_label.setText(i18n["audio_play_duration"])
        self.page.abnormal_alert_label.setText(i18n["automatic_abnormality_alert"])
        self.page.abnormal_alert_on_radio.setText(i18n["on"])
        self.page.abnormal_alert_off_radio.setText(i18n["off"])
        self.page.camera_missing_duration_label.setText(i18n["camera_missing_alert_after"])
        self.page.face_missing_duration_label.setText(i18n["face_missing_alert_after"])
        self.page.model_label.setText(i18n["download_or_update_model_files"])
        self.page.model_desc_input.setText("")
        self.page.model_btn.setText(i18n["download_or_update"])

        for idx in range(len(self.audio_file_values)):
            self.page.audio_file_combo.setItemText(idx, f'{i18n["audio"]} {idx + 1}')

        duration_keys = [
            "ten_seconds",
            "thirty_seconds",
            "one_minute",
            "five_minutes",
            "ten_minutes",
            "thirty_minutes",
            "one_hour",
            "unlimited",
        ]
        for idx, key in enumerate(duration_keys):
            self.page.audio_duration_combo.setItemText(idx, i18n[key])

        abnormal_duration_keys = [
            "ten_seconds",
            "thirty_seconds",
            "one_minute",
            "five_minutes",
            "ten_minutes",
            "thirty_minutes",
            "one_hour",
        ]
        for idx, key in enumerate(abnormal_duration_keys):
            self.page.camera_missing_duration_combo.setItemText(idx, i18n[key])
            self.page.face_missing_duration_combo.setItemText(idx, i18n[key])

        for row in self.sequence_rows:
            row["state_combo"].setItemText(0, i18n["open_eyes"])
            row["state_combo"].setItemText(1, i18n["close_eyes"])
            row["duration_label"].setText(i18n["duration_seconds"])
            row["sound_prompt_label"].setText(i18n["sound_prompt"])
            row["sound_prompt_combo"].setItemText(0, i18n["no"])
            row["sound_prompt_combo"].setItemText(1, i18n["yes"])
            row["remove_btn"].setText(i18n["remove"])
        self.update_abnormal_alert_visibility()

    def normalize_pattern(self, pattern):
        normalized = []
        for item in pattern if isinstance(pattern, list) else []:
            if not isinstance(item, dict):
                continue
            state = item.get("state")
            duration_s = item.get("duration_s")
            if state not in {"open", "closed"}:
                continue
            try:
                duration_s = float(duration_s)
            except (TypeError, ValueError):
                continue
            sound_prompt = item.get("sound_prompt")
            normalized.append({"state": state, "duration_s": duration_s, "sound_prompt": sound_prompt})

        return normalized

    def _add_sequence_row(self, state: str = "open", duration_s: float = 1.0, sound_prompt: bool = True):
        def _refresh_remove_buttons():
            enable_remove = len(self.sequence_rows) > 1
            for row in self.sequence_rows:
                row["remove_btn"].setVisible(enable_remove)
                row["remove_btn"].setEnabled(enable_remove)

        def _remove_sequence_row(row_widget: QWidget):
            if len(self.sequence_rows) <= 1:
                return

            remove_idx = -1
            for idx, row in enumerate(self.sequence_rows):
                if row["widget"] is row_widget:
                    remove_idx = idx
                    break
            if remove_idx < 0:
                return

            row = self.sequence_rows.pop(remove_idx)
            row["widget"].deleteLater()
            _refresh_remove_buttons()
            self.save_pattern()

        i18n = get_i18n(self.vm.get_config("ui.language"))

        row_widget = QWidget()
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(8)

        state_combo = QComboBox()
        state_combo.addItem(i18n["open_eyes"], "open")
        state_combo.addItem(i18n["close_eyes"], "closed")
        idx = state_combo.findData(state)
        state_combo.setCurrentIndex(0 if idx < 0 else idx)
        state_combo.setFixedSize(120, 40)

        duration_label = QLabel(i18n["duration_seconds"])
        duration_label.setObjectName("settingSubSectionTitle")
        duration_spin = NoWheelSpinBox()
        duration_spin.setDecimals(1)
        duration_spin.setSingleStep(0.5)
        duration_spin.setRange(0.5, 5.0)
        duration_spin.setValue(min(5.0, max(0.5, duration_s)))
        duration_spin.setFixedSize(100, 40)

        sound_prompt_label = QLabel(i18n["sound_prompt"])
        sound_prompt_label.setObjectName("settingSubSectionTitle")
        sound_prompt_combo = QComboBox()
        sound_prompt_combo.addItem(i18n["no"], False)
        sound_prompt_combo.addItem(i18n["yes"], True)
        sound_prompt_idx = sound_prompt_combo.findData(bool(sound_prompt))
        sound_prompt_combo.setCurrentIndex(0 if sound_prompt_idx < 0 else sound_prompt_idx)
        sound_prompt_combo.setFixedSize(100, 40)

        remove_btn = QPushButton(i18n["remove"])
        remove_btn.setObjectName("settingNormalButton")
        remove_btn.setFixedSize(160, 30)

        row_layout.addWidget(state_combo)
        row_layout.addWidget(duration_label)
        row_layout.addWidget(duration_spin)
        row_layout.addWidget(sound_prompt_label)
        row_layout.addWidget(sound_prompt_combo)
        row_layout.addStretch()
        row_layout.addWidget(remove_btn)

        row = {
            "widget": row_widget,
            "state_combo": state_combo,
            "duration_label": duration_label,
            "duration_spin": duration_spin,
            "sound_prompt_label": sound_prompt_label,
            "sound_prompt_combo": sound_prompt_combo,
            "remove_btn": remove_btn,
        }
        self.sequence_rows.append(row)
        self.page.sequence_layout.addWidget(row_widget)

        state_combo.currentIndexChanged.connect(self.save_pattern)
        duration_spin.valueChanged.connect(self.save_pattern)
        sound_prompt_combo.currentIndexChanged.connect(self.save_pattern)
        remove_btn.clicked.connect(lambda: _remove_sequence_row(row_widget))
        _refresh_remove_buttons()

    def save_pattern(self):
        sequence = []
        for row in self.sequence_rows:
            sequence.append(
                {
                    "state": row["state_combo"].currentData(),
                    "duration_s": float(row["duration_spin"].value()),
                    "sound_prompt": bool(row["sound_prompt_combo"].currentData()),
                }
            )

        self.vm.set_config("blink_call.pattern", self.normalize_pattern(sequence))

    def on_add_step(self):
        self._add_sequence_row("open", 1.0, True)
        self.save_pattern()

    def on_preview_audio(self):
        file_name = self.page.audio_file_combo.currentData()
        if not isinstance(file_name, str) or not file_name.strip():
            return

        audio_path = Path("assets") / "audio" / file_name
        if not audio_path.exists():
            return

        self.preview_sound.stop()
        self.preview_sound.setSource(QUrl.fromLocalFile(str(audio_path.resolve())))
        self.preview_sound.setLoopCount(1)
        self.preview_sound.setVolume(float(self.page.audio_volume_slider.value()) / 100.0)
        self.preview_sound.play()

    def stop_preview(self):
        self.preview_sound.stop()

    def update_audio_volume_text(self, value: int):
        self.page.audio_volume_value_label.setText(f"{int(value)}%")

    def update_sequence_visibility(self, _value=None):
        enabled = bool(self.page.enabled_radio.isChecked())
        self.page.progress_row.setVisible(enabled)
        self.page.progress_divider.setVisible(enabled)
        self.page.sequence_label.setVisible(enabled)
        self.page.sequence_host.setVisible(enabled)
        self.page.add_step_btn.setVisible(enabled)
        self.page.sequence_divider.setVisible(enabled)
        self.page.audio_switch_row.setVisible(enabled)
        self.page.audio_switch_divider.setVisible(enabled)
        self.update_audio_visibility()

    def update_audio_visibility(self, _value=None):
        call_audio_enabled = bool(self.page.enabled_radio.isChecked()) and bool(
            self.page.audio_on_radio.isChecked()
        )
        auto_alert_enabled = bool(self.page.abnormal_alert_on_radio.isChecked())
        show_audio_settings = call_audio_enabled or auto_alert_enabled
        self.page.audio_file_row.setVisible(show_audio_settings)
        self.page.audio_file_divider.setVisible(show_audio_settings)
        self.page.audio_volume_row.setVisible(show_audio_settings)
        self.page.audio_volume_divider.setVisible(show_audio_settings)
        self.page.audio_duration_row.setVisible(call_audio_enabled)
        self.page.audio_duration_divider.setVisible(call_audio_enabled)

    def update_abnormal_alert_visibility(self, _value=None):
        enabled = self.page.abnormal_alert_on_radio.isChecked()
        self.page.camera_missing_duration_row.setEnabled(enabled)
        self.page.face_missing_duration_row.setEnabled(enabled)
        self.update_audio_visibility()

    def on_model_files_status_changed(self, payload=None):
        i18n = get_i18n(self.vm.get_config("ui.language"))
        desc_text = f"{i18n.get(payload['desc_key'], '')} {payload['reason_detail']}"
        self.page.model_desc_input.setText(desc_text)
        self.page.model_btn.setEnabled(payload.get("button_enabled", False))

    def on_model_files_download_started(self):
        self.page.model_btn.setEnabled(False)
        i18n = get_i18n(self.vm.get_config("ui.language"))
        self.block_overlay.setGeometry(0, 0, self.setting_view.width(), self.setting_view.height())
        self.block_overlay.show_progress(i18n.get("downloading", ""), determinate=True)
        self.block_overlay.set_progress(0)
        self.block_overlay.show()
        self.block_overlay.raise_()

    def on_model_files_download_progress(self, progress: dict):
        value = int(max(0, min(100, progress.get("progress", 0))))
        filename = progress.get("filename", "")

        self.block_overlay.set_progress(value)
        if filename:
            i18n = get_i18n(self.vm.get_config("ui.language"))
            self.block_overlay.set_title(f'{i18n["downloading"]}\n{filename}')

    def on_model_files_download_finished(self, success: bool):
        self.block_overlay.hide()

        if success:
            self.setting_view.save_btn.click()
        else:
            self.page.model_btn.setEnabled(True)

    def on_host_resized(self):
        self.block_overlay.setGeometry(0, 0, self.setting_view.width(), self.setting_view.height())
