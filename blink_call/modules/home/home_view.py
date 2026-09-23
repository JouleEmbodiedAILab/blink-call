from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from blink_call.core.navigation import Navigation
from blink_call.modules.home.home_viewmodel import HomeViewModel
from blink_call.modules.i18n import get_i18n
from blink_call.modules.setting.setting_view import SettingView
from blink_call.utils.helper import Helper
from blink_call.widget import BlinkPatternProgressBar, InteractionBlockOverlay


class HomeView(QWidget):
    is_setting_popup = Signal(bool)

    def __init__(self, vm: HomeViewModel, nav: Navigation):
        super().__init__()
        self.vm = vm
        self.nav = nav

        self.setObjectName("homeView")

        i18n = get_i18n(self.vm.setting_vm.get_config("ui.language"))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.video_label = QLabel()
        self.video_label.setObjectName("homeVideoLabel")
        self.video_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.video_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        layout.addWidget(self.video_label)

        self.blink_progress_bar = BlinkPatternProgressBar(self)

        self.setting_btn = QPushButton(i18n["setting"], self)
        self.setting_btn.setObjectName("homeSettingBtn")
        self.setting_btn.setFixedSize(100, 40)
        self.setting_btn.move(20, 20)
        self.setting_btn.clicked.connect(self.on_open_setting_popup)

        self.setting_popup = SettingView(self.vm.setting_vm, self)
        self.setting_popup.raise_()
        self.setting_popup.setVisible(False)
        self.setting_popup.close_setting_popup.connect(self.on_close_setting_popup)

        self.exit_btn = QPushButton(i18n["exit"], self)
        self.exit_btn.setObjectName("homeExitBtn")
        self.exit_btn.setFixedSize(156, 48)
        self.exit_btn.setVisible(False)
        self.exit_btn.clicked.connect(self.vm.on_page_enter)

        self.recording_stop_btn = QPushButton("", self)
        self.recording_stop_btn.setObjectName("homeRecordStopBtn")
        self.recording_stop_btn.setFixedSize(500, 120)
        self.recording_stop_btn.setVisible(False)
        self.recording_stop_btn.clicked.connect(self.vm.stop_recording)

        self.debug_info = QPlainTextEdit(self)
        self.debug_info.setObjectName("homeDebugInfo")
        self.debug_info.setReadOnly(True)
        self.debug_info.setMaximumBlockCount(100)

        self.call_block_overlay = InteractionBlockOverlay(self)
        self.call_block_overlay.setObjectName("homeCallBlockOverlay")
        self.call_block_overlay.hide()

        self.call_close_btn = QPushButton("", self.call_block_overlay)
        self.call_close_btn.setObjectName("homeCallCloseBtn")
        self.call_close_btn.clicked.connect(self.vm.stop_call_audio)

        self.home_hint_box = QFrame(self)
        self.home_hint_box.setObjectName("homeModelFilesHint")
        self.home_hint_layout = QHBoxLayout(self.home_hint_box)
        self.home_hint_layout.setContentsMargins(6, 6, 6, 6)
        self.home_hint_layout.setSpacing(12)

        self.home_hint_icon = QLabel(self.home_hint_box)
        self.home_hint_icon.setObjectName("homeModelFilesHintIcon")
        self.home_hint_icon.setFixedSize(36, 36)
        self.home_hint_icon.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignHCenter)
        warning_icon = QPixmap("assets/icons/warning.png").scaled(
            36,
            36,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.home_hint_icon.setPixmap(warning_icon)

        self.home_hint_text = QLabel("", self.home_hint_box)
        self.home_hint_text.setObjectName("homeModelFilesHintText")
        self.home_hint_text.setWordWrap(True)

        self.home_hint_layout.addWidget(self.home_hint_icon)
        self.home_hint_layout.addWidget(self.home_hint_text, 1)
        self.home_hint_box.hide()

        self.is_setting_popup.connect(self.vm.on_listen_setting_popup)
        self.vm.frame_ready.connect(self.on_show_frame)
        self.vm.show_camera_status.connect(self.on_show_camera_status)
        self.vm.debug_mode_state.connect(self.on_set_debug_visible)
        self.vm.show_debug_msg.connect(self.on_show_debug_msg)
        self.vm.clear_debug_msg.connect(self.on_clear_debug_msg)
        self.vm.setting_vm.language_changed.connect(self.on_apply_language)
        self.vm.local_service_status.connect(self.on_set_service_mode)
        self.vm.blink_progress_updated.connect(self.on_blink_progress_updated)
        self.vm.blink_call_alert_visibility.connect(self.on_blink_call_alert_visibility)
        self.vm.auto_alarm_reason_changed.connect(self.on_auto_alarm_reason_changed)
        self.vm.home_hint.connect(self.on_home_hint)
        self.vm.recording_state_changed.connect(self.on_recording_state_changed)

        self.is_service_mode = False
        self.is_recording_mode = False
        self.on_apply_language(self.vm.setting_vm.get_config("ui.language"))

    def on_apply_language(self, language):
        i18n = get_i18n(language)
        self.setting_btn.setText(i18n["setting"])
        self.exit_btn.setText(i18n["exit"])
        self.call_close_btn.setText(i18n.get(self.vm.auto_alarm_reason_key, i18n["calling"]))

    def on_open_setting_popup(self):
        self.setting_btn.setVisible(False)
        self.setting_popup.refresh_from_local_config()
        self.setting_popup.setGeometry(0, 0, self.width(), self.height())
        self.setting_popup.show()
        self.setting_popup.raise_()
        self.is_setting_popup.emit(True)

    def on_close_setting_popup(self):
        self.setting_btn.setVisible(not self.is_service_mode and not self.is_recording_mode)
        self.is_setting_popup.emit(False)

    def on_show_frame(self, image):
        pixmap = QPixmap.fromImage(image)
        self.video_label.setPixmap(
            pixmap.scaled(
                self.video_label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        self.video_label.setText("")

    def on_show_camera_status(self, text):
        self.video_label.setPixmap(QPixmap())
        self.video_label.setText(text)

    def on_set_service_mode(self, active: bool):
        self.is_service_mode = active
        self.setting_btn.setVisible(not active and not self.is_recording_mode)
        self.exit_btn.setVisible(active)

    def on_set_debug_visible(self, visible: bool):
        self.debug_info.setVisible(visible)

    def on_clear_debug_msg(self):
        self.debug_info.clear()

    def on_show_debug_msg(self, text: str):
        self.debug_info.appendPlainText(text)

        if not self.vm.setting_vm.get_config("debug_log.save_to_local"):
            return

        log_dir = self.vm.setting_vm.get_config("debug_log.local_dir") or str(Path.home() / "Desktop")
        log_path = Path(log_dir) / "blink_call.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)

        lines = text.splitlines() or [text]
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            with log_path.open("a", encoding="utf-8") as f:
                for line in lines:
                    f.write(f"[{timestamp}] {line}\n")
        except OSError:
            return

    def on_blink_progress_updated(self, data: dict):
        visible = False if self.is_service_mode or self.is_recording_mode else data["visibility"]
        self.blink_progress_bar.setVisible(visible)
        if data["visibility"]:
            self.blink_progress_bar.set_pattern(data["pattern"])
            self.blink_progress_bar.set_progress_ratio(data["progress_ratio"])

    def on_blink_call_alert_visibility(self, visible: bool):
        if not visible or self.is_service_mode:
            self.call_block_overlay.hide()
            return

        self.call_block_overlay.setGeometry(0, 0, self.width(), self.height())
        self._position_call_close_btn()
        self.call_block_overlay.show()
        self.call_block_overlay.raise_()
        self.call_close_btn.raise_()

    def on_auto_alarm_reason_changed(self, reason_key: str):
        i18n = get_i18n(self.vm.setting_vm.get_config("ui.language"))
        self.call_close_btn.setText(i18n.get(reason_key, i18n["calling"]))

    def on_home_hint(self, data: dict):
        visible = bool(data.get("visible"))
        text = str(data.get("text") or "")
        self.home_hint_text.setText(text)
        self.home_hint_box.setVisible(visible and bool(text))
        self._position_home_hint()

    def on_recording_state_changed(self, data: dict):
        active = bool(data.get("active"))
        self.is_recording_mode = active
        self.setting_btn.setVisible(not active and not self.is_service_mode)
        self.recording_stop_btn.setVisible(active)
        if active:
            self.blink_progress_bar.setVisible(False)

        i18n = get_i18n(self.vm.setting_vm.get_config("ui.language"))
        total_text = Helper.format_hms(int(data.get("total_s") or 0))
        elapsed_text = Helper.format_hms(int(data.get("elapsed_s") or 0))
        self.recording_stop_btn.setText(f"{elapsed_text} / {total_text}\n{i18n['stop_recording']}")
        self._position_recording_stop_btn()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.setting_popup.setGeometry(0, 0, self.width(), self.height())
        self._position_exit_btn()
        self._position_debug_info()
        self._position_blink_progress_bar()
        self._position_recording_stop_btn()
        self._position_call_close_btn()
        self._position_home_hint()
        self.call_block_overlay.setGeometry(0, 0, self.width(), self.height())

    def _position_exit_btn(self):
        x = (self.width() - self.exit_btn.width()) // 2
        y = int(self.height() * 0.78)
        self.exit_btn.move(max(0, x), max(0, y))

    def _position_debug_info(self):
        panel_width = min(max(int(self.width() * 0.3), 300), 400)
        panel_height = max(int(self.height() * 0.5), 300)
        x = self.width() - panel_width - 20
        y = 20
        self.debug_info.setGeometry(max(0, x), max(0, y), panel_width, panel_height)

    def _position_blink_progress_bar(self):
        margin = 20
        bar_width = max(260, int(self.width() * 0.6))
        bar_width = min(bar_width, self.width() - margin * 2)
        bar_height = 24
        x = (self.width() - bar_width) // 2
        setting_center_y = self.setting_btn.y() + (self.setting_btn.height() // 2)
        y = setting_center_y - (bar_height // 2)
        self.blink_progress_bar.setGeometry(max(0, x), max(0, y), max(120, bar_width), bar_height)

    def _position_recording_stop_btn(self):
        x = (self.width() - self.recording_stop_btn.width()) // 2
        y = int(self.height() * 0.70)
        self.recording_stop_btn.move(max(20, x), max(20, y))

    def _position_call_close_btn(self):
        btn_width = max(int(self.width() * 0.58), 520)
        btn_width = min(btn_width, max(300, self.width() - 40))
        btn_height = min(max(int(self.height() * 0.22), 180), 280)
        x = (self.width() - btn_width) // 2
        y = int(self.height() * 0.62)
        self.call_close_btn.setGeometry(max(20, x), max(20, y), max(300, btn_width), max(140, btn_height))

    def _position_home_hint(self):
        width = min(max(int(self.width() * 0.45), 400), 600)
        margin = 20
        self.home_hint_box.setGeometry(
            margin,
            max(margin, self.height() - 96),
            width,
            76,
        )
