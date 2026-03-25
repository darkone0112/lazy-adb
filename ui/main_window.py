from __future__ import annotations

from dataclasses import dataclass
import logging
from pathlib import Path
import shlex
import sys

from PySide6.QtCore import QSize, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QCloseEvent, QMouseEvent, QResizeEvent
from PySide6.QtWidgets import QApplication, QBoxLayout, QFileDialog, QHBoxLayout, QLabel, QMainWindow, QMessageBox, QPushButton, QVBoxLayout, QWidget

from core.adb_manager import ADBManager, CommandResult, DeviceDiscovery, DeviceInfoResult
from core.device_info import DeviceInfo
from core.device_state import ConnectionMode, DeviceConnection, DeviceConnectionState, ListedDevice, filter_devices_for_mode
from core.exporter import ExportResult, SupportPackageExporter
from core.log_capture import CaptureStartResult, CaptureStopResult, LogCaptureManager
from core.platform_tools_bootstrap import PlatformToolsBootstrapResult, PlatformToolsBootstrapper
from ui.action_bar import ActionBar
from ui.advanced_window import AdvancedWindow
from ui.activity_panel import ActivityPanel
from ui.central_panel import CentralPanel
from ui.export_picker_window import ExportPickerWindow
from ui.guide_window import GuideWindow
from ui.status_panel import StatusPanel
from ui.wireless_setup_window import WirelessSetupWindow
from utils.file_helpers import get_captures_root
from utils.platform_paths import describe_host_system


@dataclass(slots=True)
class RuntimeStateSnapshot:
    adb_result: CommandResult | None
    discovery: DeviceDiscovery
    device_info_result: DeviceInfoResult | None


@dataclass(slots=True)
class AsyncADBActionResult:
    action: str
    result: object
    label: str
    command_preview: str | None = None


@dataclass(slots=True)
class BackgroundTaskResult:
    action: str
    result: object
    label: str


class DebugTitleLabel(QLabel):
    debug_toggle_requested = Signal()

    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self._click_count = 0
        self._click_timer = QTimer(self)
        self._click_timer.setSingleShot(True)
        self._click_timer.setInterval(650)
        self._click_timer.timeout.connect(self._reset_clicks)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._click_count += 1
            if self._click_count >= 3:
                self._reset_clicks()
                self.debug_toggle_requested.emit()
            else:
                self._click_timer.start()
        super().mousePressEvent(event)

    def _reset_clicks(self) -> None:
        self._click_count = 0
        self._click_timer.stop()


class RuntimeStateWorker(QThread):
    result_ready = Signal(object, bool, int)
    failed = Signal(str, bool, int)

    def __init__(
        self,
        *,
        adb_path,
        default_timeout: float,
        preferred_serial: str | None,
        mode: ConnectionMode,
        check_adb_version: bool,
        known_device_serial: str | None,
        has_device_info: bool,
        force_device_refresh: bool,
        log_changes: bool,
        generation: int,
    ) -> None:
        super().__init__()
        self._adb_path = adb_path
        self._default_timeout = default_timeout
        self._preferred_serial = preferred_serial
        self._mode = mode
        self._check_adb_version = check_adb_version
        self._known_device_serial = known_device_serial
        self._has_device_info = has_device_info
        self._force_device_refresh = force_device_refresh
        self._log_changes = log_changes
        self._generation = generation

    def run(self) -> None:
        try:
            manager = ADBManager(adb_path=self._adb_path, default_timeout=self._default_timeout)
            adb_result = manager.get_version() if self._check_adb_version else None
            discovery = manager.detect_devices(
                preferred_serial=self._preferred_serial,
                mode=self._mode,
            )
            should_fetch_info = (
                discovery.connection.state is DeviceConnectionState.READY
                and discovery.connection.serial is not None
                and (
                    self._force_device_refresh
                    or not self._has_device_info
                    or discovery.connection.serial != self._known_device_serial
                )
            )
            device_info_result = None
            if should_fetch_info and discovery.connection.serial is not None:
                device_info_result = manager.read_device_info(discovery.connection.serial)
            self.result_ready.emit(
                RuntimeStateSnapshot(
                    adb_result=adb_result,
                    discovery=discovery,
                    device_info_result=device_info_result,
                ),
                self._log_changes,
                self._generation,
            )
        except Exception as exc:  # pragma: no cover - defensive UI worker guard
            self.failed.emit(str(exc), self._log_changes, self._generation)


class ADBActionWorker(QThread):
    result_ready = Signal(object)
    failed = Signal(str, str)

    def __init__(
        self,
        *,
        action: str,
        adb_path,
        default_timeout: float,
        serial: str | None = None,
        host: str | None = None,
        port: str | None = None,
        pairing_code: str | None = None,
        target: str | None = None,
        args: list[str] | None = None,
        command_preview: str | None = None,
        label: str,
    ) -> None:
        super().__init__()
        self._action = action
        self._adb_path = adb_path
        self._default_timeout = default_timeout
        self._serial = serial
        self._host = host
        self._port = port
        self._pairing_code = pairing_code
        self._target = target
        self._args = args or []
        self._command_preview = command_preview
        self._label = label

    def run(self) -> None:
        try:
            manager = ADBManager(adb_path=self._adb_path, default_timeout=self._default_timeout)
            match self._action:
                case "pair":
                    result = manager.pair_device(self._host or "", self._port or "", self._pairing_code or "")
                case "connect":
                    result = manager.connect_device(self._host or "", self._port or "")
                case "disconnect":
                    result = manager.disconnect_device(self._target)
                case "device_info":
                    result = manager.read_device_info(self._serial or "")
                case "advanced":
                    result = manager.run(self._args, serial=self._serial, timeout=30.0)
                case _:
                    raise ValueError(f"Unsupported background ADB action: {self._action}")
            self.result_ready.emit(
                AsyncADBActionResult(
                    action=self._action,
                    result=result,
                    label=self._label,
                    command_preview=self._command_preview,
                )
            )
        except Exception as exc:  # pragma: no cover - defensive UI worker guard
            self.failed.emit(self._action, str(exc))


class BackgroundTaskWorker(QThread):
    progress = Signal(str)
    result_ready = Signal(object)
    failed = Signal(str, str)

    def __init__(
        self,
        *,
        action: str,
        label: str,
        bootstrapper: PlatformToolsBootstrapper | None = None,
        capture_manager: LogCaptureManager | None = None,
        exporter: SupportPackageExporter | None = None,
        serial: str | None = None,
        connection: DeviceConnection | None = None,
        device_info: DeviceInfo | None = None,
        log_path: Path | None = None,
        adb_version_output: str | None = None,
        destination_path: Path | None = None,
    ) -> None:
        super().__init__()
        self._action = action
        self._label = label
        self._bootstrapper = bootstrapper
        self._capture_manager = capture_manager
        self._exporter = exporter
        self._serial = serial
        self._connection = connection
        self._device_info = device_info
        self._log_path = log_path
        self._adb_version_output = adb_version_output
        self._destination_path = destination_path

    def run(self) -> None:
        try:
            match self._action:
                case "bootstrap":
                    if self._bootstrapper is None:
                        raise ValueError("Missing platform-tools bootstrapper.")
                    result = self._bootstrapper.ensure_present(progress_cb=self.progress.emit)
                case "start_capture":
                    if self._capture_manager is None or self._serial is None:
                        raise ValueError("Missing capture manager or serial.")
                    result = self._capture_manager.start_capture(self._serial)
                case "stop_capture":
                    if self._capture_manager is None:
                        raise ValueError("Missing capture manager.")
                    result = self._capture_manager.stop_capture()
                case "export":
                    if self._exporter is None or self._connection is None:
                        raise ValueError("Missing exporter context.")
                    result = self._exporter.create_package(
                        connection=self._connection,
                        device_info=self._device_info,
                        log_path=self._log_path,
                        adb_version_output=self._adb_version_output,
                        destination_path=self._destination_path,
                    )
                case _:
                    raise ValueError(f"Unsupported background task: {self._action}")
            self.result_ready.emit(
                BackgroundTaskResult(
                    action=self._action,
                    result=result,
                    label=self._label,
                )
            )
        except Exception as exc:  # pragma: no cover - defensive UI worker guard
            self.failed.emit(self._action, str(exc))


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()

        self.adb_manager = ADBManager()
        self.capture_manager = LogCaptureManager(self.adb_manager)
        self.exporter = SupportPackageExporter()
        self.platform_tools_bootstrapper = PlatformToolsBootstrapper()
        self.connection_mode = ConnectionMode.USB
        self.current_connection = DeviceConnection(state=DeviceConnectionState.NO_DEVICE)
        self.current_device_info: DeviceInfo | None = None
        self.latest_log_path: Path | None = None
        self.latest_adb_version_output = ""
        self._available_devices: list[ListedDevice] = []
        self._preferred_device_serial: str | None = None
        self._last_adb_status = ""
        self._last_connection_signature: tuple[str | None, str | None, str | None] | None = None
        self._capture_log_offset = 0
        self._capture_partial_line = ""
        self._platform_tools_bootstrap_failed = False
        self._wireless_setup_auto_opened = False
        self._wireless_no_device_poll_count = 0
        self._suspend_wireless_auto_open = False
        self._adb_version_checked = False
        self._status_refresh_thread: QThread | None = None
        self._status_refresh_worker: RuntimeStateWorker | None = None
        self._status_refresh_in_progress = False
        self._queued_refresh: tuple[bool, bool] | None = None
        self._refresh_generation = 0
        self._action_thread: QThread | None = None
        self._action_worker: ADBActionWorker | None = None
        self._command_in_progress = False
        self._background_task_thread: QThread | None = None
        self._background_task_worker: BackgroundTaskWorker | None = None
        self._background_task_in_progress = False
        self._pending_connection_feedback = False
        self._debug_log_enabled = False
        self._debug_logger: logging.Logger | None = None
        self._debug_log_handler: logging.Handler | None = None
        self._last_status_values: dict[str, tuple[str, str, str | None]] = {}
        self._last_central_panel_state: tuple[str, tuple[object, ...]] | None = None
        self._last_device_choice_state: tuple[ConnectionMode, tuple[tuple[str, str], ...], str | None, bool] | None = None
        self._last_capture_controls_state: tuple[bool, bool, bool, bool] | None = None
        self._last_activity_summary_state: tuple[str, str] | None = None
        self._last_wireless_action_state: tuple[bool, bool, bool] | None = None
        self._last_wireless_setup_enabled: bool | None = None
        self._last_advanced_target_state: tuple[str, bool] | None = None
        self._pending_wireless_connect: tuple[str, str] | None = None

        self.setWindowTitle("Lazy ADB Wizard")

        self.action_bar = ActionBar()
        self.central_panel = CentralPanel()
        self.status_panel = StatusPanel()
        self.activity_panel = ActivityPanel()
        self.guide_window: GuideWindow | None = None
        self.wireless_setup_window: WirelessSetupWindow | None = None
        self.advanced_window: AdvancedWindow | None = None
        self.export_picker_window: ExportPickerWindow | None = None
        self.usb_mode_button = QPushButton("USB")
        self.wifi_mode_button = QPushButton("Wi-Fi")
        self.status_timer = QTimer(self)
        self.status_timer.setInterval(4000)
        self.capture_tail_timer = QTimer(self)
        self.capture_tail_timer.setInterval(400)
        self._content_side_by_side = False

        self._build_layout()
        self._apply_styles()
        self._connect_signals()
        self._set_system_status(describe_host_system(), tone="info")
        self._set_capture_status("Idle", tone="warn")
        self.activity_panel.setMinimumHeight(180)
        self.central_panel.set_mode(self.connection_mode)
        self._show_guidance(self.current_connection)
        self._sync_action_state()
        self._apply_window_sizing()
        QTimer.singleShot(0, self._startup_refresh)

    def _build_layout(self) -> None:
        self.title_label = DebugTitleLabel("Lazy ADB Wizard")
        self.title_label.setObjectName("HeaderTitle")

        mode_toggle = QWidget()
        mode_layout = QHBoxLayout(mode_toggle)
        mode_layout.setContentsMargins(0, 0, 0, 0)
        mode_layout.setSpacing(6)
        self.usb_mode_button.setObjectName("ModeToggle")
        self.wifi_mode_button.setObjectName("ModeToggle")
        self.usb_mode_button.setCheckable(True)
        self.wifi_mode_button.setCheckable(True)
        self.usb_mode_button.setChecked(True)
        mode_layout.addWidget(self.usb_mode_button)
        mode_layout.addWidget(self.wifi_mode_button)

        header_widget = QWidget()
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(16)
        header_layout.addWidget(self.title_label)
        header_layout.addStretch()
        self.status_panel.setMinimumWidth(520)
        self.status_panel.setMaximumWidth(900)
        header_layout.addWidget(self.status_panel)
        header_layout.addWidget(mode_toggle)

        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)
        self.main_layout = layout
        layout.addWidget(header_widget)
        layout.addWidget(self.action_bar)
        self.content_widget = QWidget()
        self.content_layout = QBoxLayout(QBoxLayout.TopToBottom, self.content_widget)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(16)
        self.content_layout.addWidget(self.central_panel, 3)
        self.content_layout.addWidget(self.activity_panel, 2)
        layout.addWidget(self.content_widget, stretch=1)
        self.setCentralWidget(root)

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow {
                background: #0d1117;
                color: #c9d1d9;
            }
            QDialog#ExportPickerWindow, QWidget#ExportPickerRoot {
                background: #0d1117;
                color: #c9d1d9;
            }
            QMainWindow#GuideWindow, QScrollArea#GuideScroll, QWidget#GuideContainer {
                background: #0d1117;
                color: #c9d1d9;
            }
            QLabel#HeaderTitle {
                font-size: 28px;
                font-weight: 700;
                color: #f0f6fc;
            }
            QLabel#HeaderBadge {
                border-radius: 999px;
                padding: 4px 10px;
                font-size: 11px;
                font-weight: 700;
                color: #e6edf3;
                background: #1f2937;
                border: 1px solid #30363d;
            }
            QLabel#HeaderBadge[tone="violet"] {
                background: #21172f;
                border-color: #8957e5;
                color: #c297ff;
            }
            QFrame#PrimaryCard, QWidget#SidebarCard, QWidget#FeedCard {
                background: #161b22;
                border: 1px solid #30363d;
                border-radius: 16px;
            }
            QFrame#PrimaryCard {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #151b23, stop:1 #111827);
                border-color: #1f6feb;
            }
            QWidget#SidebarCard {
                background: transparent;
                border: none;
                border-radius: 0px;
            }
            QWidget#FeedCard {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #161b22, stop:1 #1b1524);
                border-color: #8957e5;
            }
            QLabel#PanelTitle, QLabel#SectionTitle {
                font-size: 18px;
                font-weight: 700;
                color: #f0f6fc;
            }
            QLabel#PanelSubtitle, QLabel#SectionSubtitle {
                color: #8b949e;
                font-size: 12px;
            }
            QLabel#SectionLabel {
                font-size: 12px;
                font-weight: 700;
                color: #58a6ff;
            }
            QLabel#HintLabel {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #17233a, stop:1 #10243f);
                border: 1px solid #1f6feb;
                border-radius: 10px;
                color: #c9d1d9;
                padding: 10px 12px;
            }
            QLabel#StepLabel {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #111827, stop:1 #161b22);
                border: 1px solid #30363d;
                border-radius: 10px;
                color: #dce6f3;
                padding: 10px 12px;
            }
            QLabel#ValueLabel {
                color: #f0f6fc;
                padding: 2px 0;
            }
            QLabel#ActivitySummary {
                background: #10161f;
                border: 1px solid #30363d;
                border-radius: 10px;
                padding: 10px 12px;
                color: #e6edf3;
            }
            QLabel#ActivitySummary[tone="info"] {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #1a1f29, stop:1 #0f253d);
                border-color: #2f81f7;
            }
            QLabel#ActivitySummary[tone="ready"] {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #13201b, stop:1 #0d2d1f);
                border-color: #3fb950;
            }
            QLabel#ActivitySummary[tone="warn"] {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2a1f12, stop:1 #2d220f);
                border-color: #d29922;
            }
            QLabel#ActivitySummary[tone="error"] {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2a1617, stop:1 #341a1d);
                border-color: #f85149;
            }
            QWidget#StatusTile {
                background: #11161d;
                border: 1px solid #30363d;
                border-radius: 10px;
            }
            QWidget#StatusTile[tone="info"] {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #152033, stop:1 #111b29);
                border-color: #2f81f7;
            }
            QWidget#StatusTile[tone="ready"] {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #163222, stop:1 #112118);
                border-color: #3fb950;
            }
            QWidget#StatusTile[tone="warn"] {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2b2114, stop:1 #211a12);
                border-color: #d29922;
            }
            QWidget#StatusTile[tone="error"] {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #35181b, stop:1 #241416);
                border-color: #f85149;
            }
            QLabel#StatusTileTitle {
                color: #8b949e;
                font-size: 9px;
                font-weight: 700;
            }
            QLabel#StatusTileValue {
                color: #f0f6fc;
                font-size: 11px;
                font-weight: 600;
            }
            QLabel#StatusTileValue[tone="ready"], QLabel#StatusDot[tone="ready"] {
                color: #3fb950;
            }
            QLabel#StatusTileValue[tone="error"], QLabel#StatusDot[tone="error"] {
                color: #f85149;
            }
            QLabel#StatusTileValue[tone="warn"], QLabel#StatusDot[tone="warn"] {
                color: #d29922;
            }
            QLabel#StatusTileValue[tone="info"], QLabel#StatusDot[tone="info"] {
                color: #79c0ff;
            }
            QLabel#StatusDot {
                font-size: 12px;
                font-weight: 700;
            }
            QPlainTextEdit {
                background: #0b1220;
                color: #79c0ff;
                border: 1px solid #30363d;
                border-radius: 12px;
                padding: 10px;
                selection-background-color: #1f6feb;
            }
            QLabel {
                color: #c9d1d9;
            }
            QFormLayout QLabel {
                color: #8b949e;
            }
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #1f6feb, stop:1 #2f81f7);
                border: 1px solid #388bfd;
                border-radius: 10px;
                color: #f0f6fc;
                padding: 10px 14px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #388bfd, stop:1 #58a6ff);
            }
            QPushButton:disabled {
                background: #21262d;
                color: #6e7681;
                border-color: #30363d;
            }
            QPushButton#ModeToggle {
                min-width: 72px;
                padding: 8px 12px;
                background: #161b22;
                border: 1px solid #30363d;
                color: #8b949e;
            }
            QPushButton#ModeToggle:hover {
                background: #1c2531;
                border-color: #58a6ff;
                color: #dce6f3;
            }
            QPushButton#ModeToggle:checked {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #1f6feb, stop:1 #2f81f7);
                border-color: #58a6ff;
                color: #f0f6fc;
            }
            QLineEdit, QComboBox {
                background: #0f1620;
                color: #e6edf3;
                border: 1px solid #30363d;
                border-radius: 10px;
                padding: 8px 10px;
            }
            QListWidget, QListWidget#ExportLogList {
                background: #0f1620;
                color: #e6edf3;
                border: 1px solid #30363d;
                border-radius: 12px;
                padding: 6px;
            }
            QListWidget::item, QListWidget#ExportLogList::item {
                padding: 10px 12px;
                border-radius: 8px;
                margin: 2px 0px;
            }
            QListWidget#ExportLogList::item {
                min-height: 48px;
            }
            QListWidget::item:selected, QListWidget#ExportLogList::item:selected {
                background: #1f6feb;
                color: #f0f6fc;
            }
            QLineEdit:focus, QComboBox:focus {
                border-color: #58a6ff;
            }
            QComboBox QAbstractItemView {
                background: #0f1620;
                color: #f0f6fc;
                border: 1px solid #30363d;
                selection-background-color: #1f6feb;
                selection-color: #f0f6fc;
            }
            QComboBox::drop-down {
                border: none;
                width: 18px;
            }
            QToolButton#CopyButton {
                min-width: 16px;
                max-width: 16px;
                min-height: 16px;
                max-height: 16px;
                border: none;
                background: transparent;
                color: #79c0ff;
                padding: 0px;
                margin: 0px;
                font-size: 9px;
                font-weight: 700;
            }
            QToolButton#CopyButton:hover {
                color: #a5d6ff;
            }
            QScrollBar:vertical {
                background: #161b22;
                width: 12px;
                margin: 4px;
            }
            QScrollBar::handle:vertical {
                background: #30363d;
                border-radius: 6px;
                min-height: 24px;
            }
            QScrollBar::handle:vertical:hover {
                background: #58a6ff;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
            QScrollBar:horizontal {
                background: #161b22;
                height: 12px;
                margin: 4px;
            }
            QScrollBar::handle:horizontal {
                background: #30363d;
                border-radius: 6px;
                min-width: 24px;
            }
            QScrollBar::handle:horizontal:hover {
                background: #58a6ff;
            }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
                width: 0px;
            }
            """
        )

    def _connect_signals(self) -> None:
        self.usb_mode_button.clicked.connect(lambda: self.on_connection_mode_selected(ConnectionMode.USB))
        self.wifi_mode_button.clicked.connect(lambda: self.on_connection_mode_selected(ConnectionMode.WIFI))
        self.action_bar.check_connection_requested.connect(self.on_check_connection)
        self.action_bar.open_guide_requested.connect(self.on_open_guide)
        self.action_bar.open_advanced_requested.connect(self.on_open_advanced)
        self.action_bar.device_selected.connect(self.on_device_selected)
        self.action_bar.refresh_device_info_requested.connect(self.on_refresh_device_info)
        self.action_bar.start_capture_requested.connect(self.on_start_capture)
        self.action_bar.stop_capture_requested.connect(self.on_stop_capture)
        self.action_bar.export_package_requested.connect(self.on_export_package)
        self.central_panel.open_wireless_setup_requested.connect(self.on_open_wireless_setup)
        self.central_panel.disconnect_requested.connect(self.on_disconnect_wireless)
        self.central_panel.device_selected.connect(self.on_device_selected)
        self.title_label.debug_toggle_requested.connect(self.on_toggle_debug_logging_requested)
        self.status_timer.timeout.connect(self.on_poll_status)
        self.capture_tail_timer.timeout.connect(self._poll_capture_log)

    def on_check_connection(self) -> None:
        self._debug_log("Manual connection check requested.")
        if not self._ensure_platform_tools_available(log_changes=True, allow_retry=True):
            return
        self._pending_connection_feedback = True
        self._refresh_runtime_state(log_changes=True, force_device_refresh=True)

    def on_refresh_device_info(self) -> None:
        if self.current_connection.state is not DeviceConnectionState.READY or not self.current_connection.serial:
            self._set_activity_summary("No ready device is selected yet.", "warn", popup=True, popup_title="Refresh Device Info")
            self.activity_panel.append_message("Check the connection first so the application can choose a device.")
            return
        self.activity_panel.append_message(f"Refreshing device information for {self.current_connection.serial}.")
        self._start_adb_action(
            action="device_info",
            label="Refresh Device Info",
            serial=self.current_connection.serial,
        )

    def on_device_selected(self, serial: str) -> None:
        if serial == self._preferred_device_serial:
            return

        self._debug_log(f"Device selection changed to {serial}.")
        self._preferred_device_serial = serial
        self.activity_panel.append_message(f"Switched active target to {serial}.")
        self._refresh_runtime_state(log_changes=True, force_device_refresh=True)
        self._sync_advanced_target()

    def on_open_guide(self) -> None:
        if self.guide_window is None:
            self.guide_window = GuideWindow(self)
            self.guide_window.setStyleSheet(self.styleSheet())
        self.guide_window.show_for_mode(self.connection_mode)

    def on_toggle_debug_logging_requested(self) -> None:
        if self._debug_log_enabled:
            return
        self._enable_debug_logging()
        self._show_feedback_popup(
            title="Debug Logging",
            message="Application debug logging is active for this session.",
            tone="warn",
        )

    def on_open_wireless_setup(self) -> None:
        self._wireless_setup_auto_opened = True
        if self.wireless_setup_window is None:
            self.wireless_setup_window = WirelessSetupWindow(self)
            self.wireless_setup_window.setStyleSheet(self.styleSheet())
            self.wireless_setup_window.pair_and_connect_requested.connect(self.on_pair_and_connect_wireless)
            self.wireless_setup_window.connect_requested.connect(self.on_connect_wireless)
        self._set_wireless_setup_controls_enabled(
            not self._platform_tools_bootstrap_failed and self.capture_manager.active_session is None
        )
        self.wireless_setup_window.show()
        self.wireless_setup_window.raise_()
        self.wireless_setup_window.activateWindow()

    def on_open_advanced(self) -> None:
        if self.advanced_window is None:
            self.advanced_window = AdvancedWindow(self)
            self.advanced_window.setStyleSheet(self.styleSheet())
            self.advanced_window.command_requested.connect(self.on_run_advanced_command)
        self._sync_advanced_target()
        self.advanced_window.show()
        self.advanced_window.raise_()
        self.advanced_window.activateWindow()

    def on_connection_mode_selected(self, mode: ConnectionMode) -> None:
        if self.capture_manager.active_session is not None or self._is_busy() or mode is self.connection_mode:
            self._sync_mode_buttons()
            return

        self._debug_log(f"Switching connection mode to {mode.value}.")
        self.connection_mode = mode
        self._refresh_generation += 1
        self._wireless_setup_auto_opened = False
        self._wireless_no_device_poll_count = 0
        self._suspend_wireless_auto_open = False
        self._pending_wireless_connect = None
        self._preferred_device_serial = None
        self._available_devices = []
        self.current_device_info = None
        self.current_connection = DeviceConnection(state=DeviceConnectionState.NO_DEVICE)
        self._adb_version_checked = False
        self._set_device_choices(choices=[], selected_serial=None, enabled=False)
        self.central_panel.set_mode(mode)
        self._show_guidance(self.current_connection)
        self._set_activity_summary(
            "Wireless ADB mode is active. Use Connect Device from the main panel."
            if mode is ConnectionMode.WIFI
            else "USB ADB mode is active. Connect a device by cable or check the current connection."
            ,
            "info",
        )
        self.activity_panel.append_message(
            "Switched to Wireless ADB mode."
            if mode is ConnectionMode.WIFI
            else "Switched to USB ADB mode."
        )
        self._sync_mode_buttons()
        self._refresh_runtime_state(log_changes=True, force_device_refresh=True)

    def on_pair_wireless(self, host: str, port: str, pairing_code: str) -> None:
        if self.connection_mode is not ConnectionMode.WIFI:
            self._pending_wireless_connect = None
            return
        if not host or not port or not pairing_code:
            self._pending_wireless_connect = None
            self._set_activity_summary(
                "Wireless pairing needs host, pairing port, and pairing code.",
                "warn",
                popup=True,
                popup_title="Wireless Pairing",
            )
            return
        if not port.isdigit():
            self._pending_wireless_connect = None
            self._set_activity_summary("The pairing port must be numeric.", "warn", popup=True, popup_title="Wireless Pairing")
            return
        if not self._ensure_platform_tools_available(log_changes=True, allow_retry=True):
            self._pending_wireless_connect = None
            return

        self._debug_log(f"Starting wireless pairing for {host}:{port}.")
        self.activity_panel.append_message(f"Pairing with {host}:{port}.")
        self._start_adb_action(
            action="pair",
            label="Wireless Pairing",
            host=host,
            port=port,
            pairing_code=pairing_code,
        )

    def on_pair_and_connect_wireless(
        self,
        host: str,
        pair_port: str,
        pairing_code: str,
        connect_port: str,
    ) -> None:
        if self.connection_mode is not ConnectionMode.WIFI:
            return
        if not host or not pair_port or not pairing_code or not connect_port:
            self._set_activity_summary(
                "Connect Device needs host, pairing port, pairing code, and connect port.",
                "warn",
                popup=True,
                popup_title="Connect Device",
            )
            return
        if not pair_port.isdigit():
            self._set_activity_summary("The pairing port must be numeric.", "warn", popup=True, popup_title="Connect Device")
            return
        if not connect_port.isdigit():
            self._set_activity_summary("The connect port must be numeric.", "warn", popup=True, popup_title="Connect Device")
            return
        self._pending_wireless_connect = (host, connect_port)
        self._debug_log(f"Queued Connect Device for {host} (pair={pair_port}, connect={connect_port}).")
        self.activity_panel.append_message(
            f"Pairing and connecting to {host}. Pair port: {pair_port}. Connect port: {connect_port}."
        )
        self.on_pair_wireless(host, pair_port, pairing_code)

    def on_connect_wireless(self, host: str, port: str) -> None:
        if self.connection_mode is not ConnectionMode.WIFI:
            return
        if self._pending_wireless_connect == (host, port):
            self._pending_wireless_connect = None
        if not host or not port:
            self._set_activity_summary("Wireless connect needs a host and connect port.", "warn", popup=True, popup_title="Wireless Connect")
            return
        if not port.isdigit():
            self._set_activity_summary("The connect port must be numeric.", "warn", popup=True, popup_title="Wireless Connect")
            return
        if not self._ensure_platform_tools_available(log_changes=True, allow_retry=True):
            return

        endpoint = f"{host}:{port}"
        self._debug_log(f"Starting wireless connect for {endpoint}.")
        self.activity_panel.append_message(f"Connecting to {endpoint}.")
        self._start_adb_action(
            action="connect",
            label="Wireless Connect",
            host=host,
            port=port,
        )

    def on_disconnect_wireless(self, target: str) -> None:
        if self.connection_mode is not ConnectionMode.WIFI:
            return
        self._pending_wireless_connect = None

        endpoint = target.strip() or (self.current_connection.serial or "")
        if not endpoint:
            self._set_activity_summary(
                "Provide a connected wireless endpoint before disconnecting.",
                "warn",
                popup=True,
                popup_title="Wireless Disconnect",
            )
            return
        if not self._ensure_platform_tools_available(log_changes=True, allow_retry=True):
            return

        self._debug_log(f"Starting wireless disconnect for {endpoint}.")
        self.activity_panel.append_message(f"Disconnecting and forgetting guidance for {endpoint}.")
        self._start_adb_action(
            action="disconnect",
            label="Disconnect / Forget Wireless Device",
            target=endpoint,
        )

    def on_run_advanced_command(self, command_text: str) -> None:
        if self.current_connection.state is not DeviceConnectionState.READY or not self.current_connection.serial:
            self._set_activity_summary("No ready device is selected for Advanced commands.", "warn", popup=True, popup_title="Advanced")
            return

        try:
            args = shlex.split(command_text)
        except ValueError as exc:
            self._set_activity_summary("The Advanced command could not be parsed.", "error")
            self._show_feedback_popup(title="Advanced", message=str(exc), tone="error")
            return

        if not args:
            return
        if args[0] == "adb":
            args = args[1:]
        if len(args) >= 2 and args[0] == "-s":
            args = args[2:]
        if not args:
            self._set_activity_summary("No ADB subcommand was provided.", "warn", popup=True, popup_title="Advanced")
            return

        command_preview = " ".join(args)
        self._debug_log(f"Starting advanced command: {command_preview}")
        self._start_adb_action(
            action="advanced",
            label="Advanced",
            serial=self.current_connection.serial,
            args=args,
            command_preview=command_preview,
        )

    def on_start_capture(self) -> None:
        if self.current_connection.state is not DeviceConnectionState.READY or not self.current_connection.serial:
            self._set_activity_summary("No ready device is available for capture.", "warn", popup=True, popup_title="Start Capture")
            self.activity_panel.append_message("Connect and authorize a device before starting logcat capture.")
            return
        self._debug_log(f"Starting capture for {self.current_connection.serial}.")
        self.activity_panel.append_message(f"Starting log capture for {self.current_connection.serial}.")
        self._start_background_task(
            action="start_capture",
            label="Start Capture",
            serial=self.current_connection.serial,
        )

    def on_stop_capture(self) -> None:
        self._debug_log("Stopping capture.")
        self.activity_panel.append_message("Stopping log capture.")
        self._start_background_task(
            action="stop_capture",
            label="Stop Capture",
        )

    def on_export_package(self) -> None:
        log_paths = self._list_available_capture_logs()
        if not log_paths:
            self._show_feedback_popup(
                title="Export Package",
                message="No captured log files are available yet.",
                tone="warn",
            )
            return
        self._open_export_picker(log_paths)

    def on_poll_status(self) -> None:
        if self._is_busy():
            return
        self._refresh_runtime_state(log_changes=False, force_device_refresh=False)

    def _startup_refresh(self) -> None:
        if self._ensure_platform_tools_available(log_changes=True, allow_retry=True):
            self._refresh_runtime_state(log_changes=True, force_device_refresh=True)
        if not self.status_timer.isActive():
            self.status_timer.start()

    def _ensure_platform_tools_available(self, *, log_changes: bool, allow_retry: bool) -> bool:
        if self.platform_tools_bootstrapper.is_installed():
            self._platform_tools_bootstrap_failed = False
            return True

        if self._platform_tools_bootstrap_failed and not allow_retry:
            self._available_devices = []
            self._preferred_device_serial = None
            self._adb_version_checked = False
            self._set_device_choices(choices=[], selected_serial=None, enabled=False)
            self._set_wireless_action_state(
                has_device=False,
                pairing_enabled=False,
                disconnect_enabled=False,
            )
            self._set_adb_status(
                "Inactive",
                tone="error",
                tooltip="Bundled platform-tools are still missing.",
            )
            return False

        if self._background_task_in_progress:
            return False

        self._set_activity_summary("Bundled platform-tools are missing. Downloading the package for this system.", "warn")
        self._set_wireless_action_state(
            has_device=False,
            pairing_enabled=False,
            disconnect_enabled=False,
        )
        self._set_adb_status("Inactive", tone="error", tooltip="Downloading platform-tools...")
        self._set_connection_status(
            "Disconnected",
            tone="error",
            tooltip="Waiting for platform-tools download.",
        )

        if log_changes:
            self.activity_panel.append_message("Bundled platform-tools are not present. Starting first-run download.")
        self._start_background_task(
            action="bootstrap",
            label="Platform-Tools Download",
        )
        return False

    def _refresh_runtime_state(self, *, log_changes: bool, force_device_refresh: bool) -> None:
        if not self._ensure_platform_tools_available(log_changes=log_changes, allow_retry=False):
            self._sync_action_state()
            return

        if self._is_busy():
            if self._queued_refresh is None:
                self._queued_refresh = (log_changes, force_device_refresh)
            else:
                queued_log_changes, queued_force_refresh = self._queued_refresh
                self._queued_refresh = (
                    queued_log_changes or log_changes,
                    queued_force_refresh or force_device_refresh,
                )
            return

        if self._status_refresh_in_progress:
            if self._queued_refresh is None:
                self._queued_refresh = (log_changes, force_device_refresh)
            else:
                queued_log_changes, queued_force_refresh = self._queued_refresh
                self._queued_refresh = (
                    queued_log_changes or log_changes,
                    queued_force_refresh or force_device_refresh,
                )
            return

        self._debug_log(
            f"Scheduling runtime refresh (mode={self.connection_mode.value}, force_device_refresh={force_device_refresh}, "
            f"log_changes={log_changes})."
        )
        self._start_runtime_state_worker(log_changes=log_changes, force_device_refresh=force_device_refresh)

    def _start_runtime_state_worker(self, *, log_changes: bool, force_device_refresh: bool) -> None:
        self._debug_log("Runtime refresh worker started.")
        self._status_refresh_in_progress = True
        worker = RuntimeStateWorker(
            adb_path=self.adb_manager.adb_path,
            default_timeout=self.adb_manager.default_timeout,
            preferred_serial=self._preferred_device_serial,
            mode=self.connection_mode,
            check_adb_version=not self._adb_version_checked,
            known_device_serial=self.current_connection.serial,
            has_device_info=self.current_device_info is not None,
            force_device_refresh=force_device_refresh,
            log_changes=log_changes,
            generation=self._refresh_generation,
        )
        worker.setParent(self)
        worker.result_ready.connect(self._on_runtime_state_ready)
        worker.failed.connect(self._on_runtime_state_failed)
        self._status_refresh_worker = worker
        self._status_refresh_thread = worker
        worker.finished.connect(self._clear_runtime_state_worker)
        worker.start()

    def _on_runtime_state_ready(self, snapshot: RuntimeStateSnapshot, log_changes: bool, generation: int) -> None:
        if generation != self._refresh_generation:
            self._complete_runtime_state_refresh()
            return
        self._debug_log(
            f"Runtime refresh completed with state={snapshot.discovery.connection.state.value}, "
            f"serial={snapshot.discovery.connection.serial}."
        )
        adb_result = snapshot.adb_result
        if adb_result is not None:
            adb_status = self._describe_adb_status(adb_result)
            self._set_adb_status(
                "Active" if adb_result.success else "Inactive",
                tone="ready" if adb_result.success else "error",
                tooltip=adb_status,
            )
            if adb_result.success:
                self.latest_adb_version_output = adb_result.stdout
                self._adb_version_checked = True
            else:
                self._adb_version_checked = False
        elif snapshot.discovery.command_result.success:
            adb_status = self._last_adb_status or "ADB is available."
            self._set_adb_status("Active", tone="ready", tooltip=adb_status)
        else:
            adb_status = snapshot.discovery.command_result.describe()
            self._set_adb_status("Inactive", tone="error", tooltip=adb_status)
            self._adb_version_checked = False

        adb_changed = adb_status != self._last_adb_status
        if adb_changed:
            self._last_adb_status = adb_status
            if log_changes:
                self.activity_panel.append_message(adb_status)

        if not snapshot.discovery.command_result.success and not snapshot.discovery.devices:
            self._available_devices = []
            self._preferred_device_serial = None
            self._set_device_choices(choices=[], selected_serial=None, enabled=False)
            self._set_wireless_action_state(
                has_device=False,
                pairing_enabled=False,
                disconnect_enabled=False,
            )
            self.current_connection = DeviceConnection(
                state=DeviceConnectionState.ERROR,
                detail=snapshot.discovery.command_result.describe(),
            )
            self.current_device_info = None
            self._set_connection_status(
                "Disconnected",
                tone="error",
                tooltip=self._friendly_state_summary(self.current_connection),
            )
            if self.capture_manager.active_session is None:
                self._show_guidance(self.current_connection)
            if log_changes:
                self._set_activity_summary("ADB is unavailable, so device detection could not continue.", "error")
            if self._pending_connection_feedback:
                self._show_feedback_popup(
                    title="Connection Status",
                    message=self._friendly_state_summary(self.current_connection),
                    tone="warn",
                )
                self._pending_connection_feedback = False
            self._complete_runtime_state_refresh()
            return

        discovery = snapshot.discovery
        self._debug_log(
            "Runtime discovery devices: "
            + (
                ", ".join(f"{device.serial} [{device.raw_state}]" for device in discovery.devices)
                if discovery.devices
                else "<none>"
            )
            + f" | mode={self.connection_mode.value} | preferred={self._preferred_device_serial}"
        )
        self._available_devices = filter_devices_for_mode(discovery.devices, self.connection_mode)
        self._debug_log(
            "Runtime visible devices: "
            + (
                ", ".join(f"{device.serial} [{device.raw_state}]" for device in self._available_devices)
                if self._available_devices
                else "<none>"
            )
        )
        if self.connection_mode is ConnectionMode.WIFI:
            if self._available_devices:
                self._wireless_no_device_poll_count = 0
                self._wireless_setup_auto_opened = False
            else:
                self._wireless_no_device_poll_count += 1
            if (
                not self._available_devices
                and not self._wireless_setup_auto_opened
                and not self._suspend_wireless_auto_open
                and self._wireless_no_device_poll_count >= 2
            ):
                self.on_open_wireless_setup()
        self._set_wireless_action_state(
            has_device=self.connection_mode is ConnectionMode.WIFI and bool(self._available_devices),
            pairing_enabled=self.connection_mode is ConnectionMode.WIFI and self.capture_manager.active_session is None,
            disconnect_enabled=(
                self.connection_mode is ConnectionMode.WIFI
                and self.capture_manager.active_session is None
                and discovery.connection.serial is not None
            ),
        )
        self._sync_advanced_target()
        previous_signature = self._last_connection_signature
        current_signature = (
            discovery.connection.state.value,
            discovery.connection.serial,
            discovery.connection.detail,
        )
        connection_changed = current_signature != previous_signature
        self._last_connection_signature = current_signature
        self.current_connection = discovery.connection
        self._debug_log(
            f"Runtime selected connection: state={self.current_connection.state.value}, "
            f"serial={self.current_connection.serial}, raw_state={self.current_connection.raw_state}, "
            f"detail={self.current_connection.detail}"
        )
        if self.current_connection.serial is not None:
            self._preferred_device_serial = self.current_connection.serial
        elif not self._available_devices:
            self._preferred_device_serial = None

        self._set_device_choices(
            choices=[(self._format_device_choice(device), device.serial) for device in self._available_devices],
            selected_serial=self._preferred_device_serial,
            enabled=self.capture_manager.active_session is None,
        )
        self._set_connection_status(
            "Connected" if self.current_connection.state is DeviceConnectionState.READY else "Disconnected",
            tone=self._connection_tone(self.current_connection),
            tooltip=self._friendly_state_summary(self.current_connection),
        )

        if self.current_connection.state is DeviceConnectionState.READY and self.current_connection.serial:
            if connection_changed and log_changes:
                self.activity_panel.append_message(
                    f"Detected device {self.current_connection.serial} ({self.current_connection.raw_state})."
                )
            if snapshot.device_info_result is not None:
                self._apply_device_info_result(
                    snapshot.device_info_result,
                    announce_success=log_changes,
                )
            elif self.capture_manager.active_session is None and self.current_device_info is not None:
                self._show_device_info(self.current_device_info)
            self._set_activity_summary("Device detection is active and up to date.", "ready")
            self._pending_connection_feedback = False
        else:
            self.current_device_info = None
            if self.capture_manager.active_session is None:
                self._show_guidance(self.current_connection)
            if connection_changed and log_changes:
                self.activity_panel.append_message(self._friendly_state_summary(self.current_connection))
            if self.current_connection.state is DeviceConnectionState.NO_DEVICE:
                self._set_activity_summary(
                    "No wireless device was detected. Use Connect Device if needed."
                    if self.connection_mode is ConnectionMode.WIFI
                    else "No ready device was detected. Follow the setup guidance if needed.",
                    "warn",
                )
            else:
                self._set_activity_summary(
                    self._friendly_state_summary(self.current_connection),
                    self._connection_tone(self.current_connection),
                )
            if self._pending_connection_feedback:
                self._show_feedback_popup(
                    title="Connection Status",
                    message=self._friendly_state_summary(self.current_connection),
                    tone="warn",
                )
                self._pending_connection_feedback = False

        self._complete_runtime_state_refresh()

    def _on_runtime_state_failed(self, message: str, log_changes: bool, generation: int) -> None:
        if generation != self._refresh_generation:
            self._complete_runtime_state_refresh()
            return
        self._debug_log(f"Runtime refresh failed: {message}")
        self._adb_version_checked = False
        self.current_connection = DeviceConnection(
            state=DeviceConnectionState.ERROR,
            detail=message,
        )
        self._set_adb_status("Inactive", tone="error", tooltip=message)
        self._set_connection_status("Disconnected", tone="error", tooltip=message)
        if self.capture_manager.active_session is None:
            self._show_guidance(self.current_connection)
        if log_changes:
            self._set_activity_summary("Background device refresh failed.", "error")
            self.activity_panel.append_message(message)
        if self._pending_connection_feedback:
            self._show_feedback_popup(title="Connection Status", message=message, tone="warn")
            self._pending_connection_feedback = False
        self._complete_runtime_state_refresh()

    def _start_background_task(
        self,
        *,
        action: str,
        label: str,
        serial: str | None = None,
        connection: DeviceConnection | None = None,
        device_info: DeviceInfo | None = None,
        log_path: Path | None = None,
        adb_version_output: str | None = None,
        destination_path: Path | None = None,
    ) -> None:
        if self._background_task_in_progress:
            self._set_activity_summary(f"{label} is already running.", "warn", popup=True, popup_title=label)
            return
        self._debug_log(f"Background task started: {action}")
        self._background_task_in_progress = True
        worker = BackgroundTaskWorker(
            action=action,
            label=label,
            bootstrapper=self.platform_tools_bootstrapper if action == "bootstrap" else None,
            capture_manager=self.capture_manager if action in {"start_capture", "stop_capture"} else None,
            exporter=self.exporter if action == "export" else None,
            serial=serial,
            connection=connection,
            device_info=device_info,
            log_path=log_path,
            adb_version_output=adb_version_output,
            destination_path=destination_path,
        )
        worker.setParent(self)
        worker.progress.connect(self._on_background_task_progress)
        worker.result_ready.connect(self._on_background_task_finished)
        worker.failed.connect(self._on_background_task_failed)
        self._background_task_worker = worker
        self._background_task_thread = worker
        worker.finished.connect(self._clear_background_task_worker)
        self._sync_action_state()
        worker.start()

    def _on_background_task_progress(self, message: str) -> None:
        self.activity_panel.append_message(message)

    def _on_background_task_finished(self, outcome: BackgroundTaskResult) -> None:
        self._debug_log(f"Background task finished: {outcome.action}")
        self._background_task_in_progress = False
        match outcome.action:
            case "bootstrap":
                result = outcome.result
                self._handle_bootstrap_result(result)
            case "start_capture":
                result = outcome.result
                self._handle_start_capture_result(result)
            case "stop_capture":
                result = outcome.result
                self._handle_stop_capture_result(result)
            case "export":
                result = outcome.result
                self._handle_export_result(result)
            case _:
                self.activity_panel.append_message(f"Completed background task: {outcome.label}.")
        self._sync_action_state()
        self._drain_queued_refresh_if_idle()

    def _on_background_task_failed(self, action: str, message: str) -> None:
        self._debug_log(f"Background task failed: {action} -> {message}")
        self._background_task_in_progress = False
        self._set_activity_summary(f"{action.replace('_', ' ').title()} failed.", "error")
        self.activity_panel.append_message(message)
        self._show_feedback_popup(title="Background Task", message=message, tone="error")
        self._sync_action_state()
        self._drain_queued_refresh_if_idle()

    def _clear_background_task_worker(self) -> None:
        self._background_task_thread = None
        self._background_task_worker = None

    def _start_adb_action(
        self,
        *,
        action: str,
        label: str,
        serial: str | None = None,
        host: str | None = None,
        port: str | None = None,
        pairing_code: str | None = None,
        target: str | None = None,
        args: list[str] | None = None,
        command_preview: str | None = None,
    ) -> None:
        if self._command_in_progress:
            self._set_activity_summary(f"{label} is already running.", "warn", popup=True, popup_title=label)
            return
        self._debug_log(f"ADB action started: {action}")
        self._command_in_progress = True
        worker = ADBActionWorker(
            action=action,
            adb_path=self.adb_manager.adb_path,
            default_timeout=self.adb_manager.default_timeout,
            serial=serial,
            host=host,
            port=port,
            pairing_code=pairing_code,
            target=target,
            args=args,
            command_preview=command_preview,
            label=label,
        )
        worker.setParent(self)
        worker.result_ready.connect(self._on_adb_action_finished)
        worker.failed.connect(self._on_adb_action_failed)
        self._action_worker = worker
        self._action_thread = worker
        worker.finished.connect(self._clear_adb_action_worker)
        self._sync_action_state()
        worker.start()

    def _handle_bootstrap_result(self, result: PlatformToolsBootstrapResult) -> None:
        if result.success:
            self._platform_tools_bootstrap_failed = False
            if result.downloaded:
                self.activity_panel.append_message(result.message)
            self._set_activity_summary("Platform-tools are ready.", "ready")
            self._set_wireless_action_state(
                has_device=bool(self._available_devices),
                pairing_enabled=self.capture_manager.active_session is None,
                disconnect_enabled=self.capture_manager.active_session is None and self.current_connection.serial is not None,
            )
            self._set_adb_status(
                "Active",
                tone="ready",
                tooltip="Bundled platform-tools are installed.",
            )
            self._refresh_runtime_state(log_changes=True, force_device_refresh=True)
            if not self.status_timer.isActive():
                self.status_timer.start()
            return

        self._platform_tools_bootstrap_failed = True
        self._available_devices = []
        self._preferred_device_serial = None
        self._adb_version_checked = False
        self._set_device_choices(choices=[], selected_serial=None, enabled=False)
        self._set_wireless_action_state(
            has_device=False,
            pairing_enabled=False,
            disconnect_enabled=False,
        )
        self.current_connection = DeviceConnection(
            state=DeviceConnectionState.ERROR,
            detail=result.message,
        )
        self._set_activity_summary("Platform-tools download failed. Retry after restoring network access.", "error")
        self.activity_panel.append_message(result.message)
        self._show_feedback_popup(title="Platform-Tools Download", message=result.message, tone="error")
        self._set_adb_status("Inactive", tone="error", tooltip="Platform-tools download failed.")
        self._set_connection_status(
            "Disconnected",
            tone="error",
            tooltip="ADB is unavailable until platform-tools are installed.",
        )
        self._show_guidance(self.current_connection)
        if self._pending_connection_feedback:
            self._show_feedback_popup(title="Connection Status", message=result.message, tone="warn")
            self._pending_connection_feedback = False

    def _handle_start_capture_result(self, result: CaptureStartResult) -> None:
        if not result.success or result.session is None:
            self._set_activity_summary("Log capture could not be started.", "error")
            self.activity_panel.append_message(result.message)
            self._show_feedback_popup(title="Start Capture", message=result.message, tone="error")
            return

        self._show_capture_state(
            self.current_device_info.serial_number if self.current_device_info is not None else result.session.serial,
            str(result.session.log_path),
            "Logcat is being written live to disk. Reproduce the issue, then stop the capture.",
        )
        self._set_activity_summary("Log capture is running.", "ready")
        self.activity_panel.append_message(result.message)
        self.latest_log_path = result.session.log_path
        self._capture_log_offset = 0
        self._capture_partial_line = ""
        self.capture_tail_timer.start()
        self._set_capture_status(f"Capturing to {result.session.log_path.name}", tone="ready")

    def _handle_stop_capture_result(self, result: CaptureStopResult) -> None:
        self._flush_capture_log(final=True)
        self.capture_tail_timer.stop()
        if not result.success:
            self._set_activity_summary("Log capture could not be stopped cleanly.", "error")
            self.activity_panel.append_message(result.message)
            if result.stderr.strip():
                self.activity_panel.append_message(result.stderr.strip())
            self._show_feedback_popup(title="Stop Capture", message=result.message, tone="error")
            self._set_capture_status("Capture stopped with issues", tone="error")
            return

        self.activity_panel.clear_feed()
        self.latest_log_path = result.log_path or self.latest_log_path
        if self.current_device_info is not None:
            self._show_device_info(self.current_device_info)
        elif self.current_connection.serial:
            self._show_ready_without_info(
                self.current_connection.serial,
                "Capture finished. Refresh device information if you want the latest details in the export package.",
            )
        else:
            self._show_guidance(self.current_connection)

        self._set_activity_summary("Log capture stopped and the file is ready for export.", "warn")
        self.activity_panel.append_message(result.message)
        if result.stderr.strip():
            self.activity_panel.append_message(result.stderr.strip())
        self._set_capture_status("Idle", tone="warn")
        self._show_capture_complete_popup()

    def _handle_export_result(self, result: ExportResult) -> None:
        if result.success:
            self._set_activity_summary("Support package created successfully.", "ready")
            self.activity_panel.append_message(result.message)
            return
        self._set_activity_summary("Support package could not be created.", "error")
        self.activity_panel.append_message(result.message)
        self._show_feedback_popup(title="Export Package", message=result.message, tone="error")

    def _on_adb_action_finished(self, outcome: AsyncADBActionResult) -> None:
        self._debug_log(f"ADB action finished: {outcome.action}")
        self._command_in_progress = False
        queued_connect: tuple[str, str] | None = None
        match outcome.action:
            case "pair":
                result = outcome.result
                self.activity_panel.append_message(self._describe_command_feedback(result))
                if result.success:
                    if self._pending_wireless_connect is not None:
                        host, port = self._pending_wireless_connect
                        self._pending_wireless_connect = None
                        self._set_activity_summary("Wireless pairing succeeded. Connecting now.", "ready")
                        self.activity_panel.append_message(f"Pairing succeeded. Connecting to {host}:{port}.")
                        queued_connect = (host, port)
                    else:
                        self._set_activity_summary("Wireless pairing succeeded. Connect using the device's debug port.", "ready")
                else:
                    self._pending_wireless_connect = None
                    self._set_activity_summary("Wireless pairing failed.", "error")
                    self._show_feedback_popup(title=outcome.label, message=result.describe(), tone="error")
            case "connect":
                result = outcome.result
                self.activity_panel.append_message(self._describe_command_feedback(result))
                if not result.success:
                    self._pending_wireless_connect = None
                    self._set_activity_summary("Wireless connection failed.", "error")
                    self._show_feedback_popup(title=outcome.label, message=result.describe(), tone="error")
                else:
                    first_target = result.command[-1] if result.command else None
                    if first_target:
                        self._preferred_device_serial = first_target
                    self._set_activity_summary("Wireless connection succeeded.", "ready")
                    if self.wireless_setup_window is not None:
                        self.wireless_setup_window.close()
                    self._refresh_runtime_state(log_changes=True, force_device_refresh=True)
            case "disconnect":
                result = outcome.result
                self.activity_panel.append_message(self._describe_command_feedback(result))
                if result.success:
                    self._preferred_device_serial = None
                    self._set_activity_summary("Wireless device disconnected. Remove this computer from the phone if you want to forget it fully.", "warn")
                    self._suspend_wireless_auto_open = True
                    self._show_feedback_popup(
                        title=outcome.label,
                        message=(
                            "The active wireless ADB session was disconnected.\n\n"
                            "This does not remove the pairing stored on the Android device.\n"
                            "To fully forget this computer, open Wireless debugging on the phone, "
                            "open the paired devices/computers list, and remove this computer there."
                        ),
                        tone="warn",
                    )
                    self._suspend_wireless_auto_open = False
                else:
                    self._set_activity_summary("Wireless disconnect failed.", "error")
                    self._show_feedback_popup(title=outcome.label, message=result.describe(), tone="error")
                self._refresh_runtime_state(log_changes=True, force_device_refresh=True)
            case "device_info":
                result = outcome.result
                self._apply_device_info_result(result, announce_success=True)
                self._set_connection_status(
                    "Connected" if self.current_connection.state is DeviceConnectionState.READY else "Disconnected",
                    tone=self._connection_tone(self.current_connection),
                    tooltip=self._friendly_state_summary(self.current_connection),
                )
                self._sync_advanced_target()
            case "advanced":
                result = outcome.result
                command_preview = outcome.command_preview or ""
                output_parts: list[str] = [f"$ adb -s {self.current_connection.serial} {command_preview}"]
                if result.stdout.strip():
                    output_parts.append(result.stdout.rstrip())
                if result.stderr.strip():
                    output_parts.append(result.stderr.rstrip())
                if not result.stdout.strip() and not result.stderr.strip():
                    output_parts.append(result.describe())
                output_text = "\n".join(output_parts)
                if self.advanced_window is not None:
                    self.advanced_window.append_output(output_text)
                self.activity_panel.append_message(f"Advanced command executed: {command_preview}")
                if not result.success:
                    self._set_activity_summary("The Advanced command failed.", "error")
                    self._show_feedback_popup(title=outcome.label, message=result.describe(), tone="error")
            case _:
                self.activity_panel.append_message(f"Completed background action: {outcome.label}.")
        self._sync_action_state()
        self._drain_queued_refresh_if_idle()
        if queued_connect is not None:
            host, port = queued_connect
            QTimer.singleShot(0, lambda: self.on_connect_wireless(host, port))

    def _on_adb_action_failed(self, action: str, message: str) -> None:
        self._debug_log(f"ADB action failed: {action} -> {message}")
        self._command_in_progress = False
        self._set_activity_summary(f"{action.replace('_', ' ').title()} failed.", "error")
        self.activity_panel.append_message(message)
        self._show_feedback_popup(title="ADB Action", message=message, tone="error")
        self._sync_action_state()
        self._drain_queued_refresh_if_idle()

    def _clear_adb_action_worker(self) -> None:
        self._action_thread = None
        self._action_worker = None

    def _clear_runtime_state_worker(self) -> None:
        self._status_refresh_thread = None
        self._status_refresh_worker = None

    def _complete_runtime_state_refresh(self) -> None:
        self._status_refresh_in_progress = False
        self._sync_action_state()
        self._drain_queued_refresh_if_idle()

    def _drain_queued_refresh_if_idle(self) -> None:
        if self._queued_refresh is None or self._status_refresh_in_progress or self._is_busy():
            return
        if self._queued_refresh is None:
            return
        log_changes, force_device_refresh = self._queued_refresh
        self._queued_refresh = None
        QTimer.singleShot(
            0,
            lambda: self._refresh_runtime_state(
                log_changes=log_changes,
                force_device_refresh=force_device_refresh,
            ),
        )

    def _apply_device_info_result(self, result: DeviceInfoResult, *, announce_success: bool) -> None:
        if result.device_info is not None:
            self.current_device_info = result.device_info
            if self.capture_manager.active_session is None:
                self._show_device_info(result.device_info)
            if announce_success:
                self.activity_panel.append_message("Device information loaded successfully.")
            self._set_activity_summary("Device information is up to date.", "ready")
            self._set_connection_status(
                "Connected" if self.current_connection.state is DeviceConnectionState.READY else "Disconnected",
                tone=self._connection_tone(self.current_connection),
                tooltip=self._friendly_state_summary(self.current_connection),
            )
            self._sync_action_state()
            return

        self.current_device_info = None
        detail_message = result.command_result.describe()
        if self.current_connection.serial and self.capture_manager.active_session is None:
            self._show_ready_without_info(
                self.current_connection.serial,
                detail_message,
            )
        self._set_activity_summary(
            "A target is connected, but it did not provide usable Android device information.",
            "error",
        )
        self.activity_panel.append_message(detail_message)
        self._set_connection_status(
            "Connected" if self.current_connection.state is DeviceConnectionState.READY else "Disconnected",
            tone=self._connection_tone(self.current_connection),
            tooltip=self._friendly_state_summary(self.current_connection),
        )
        self._sync_action_state()

    def _friendly_state_summary(self, connection: DeviceConnection) -> str:
        match connection.state:
            case DeviceConnectionState.NO_DEVICE:
                return (
                    "No wireless device is connected yet."
                    if self.connection_mode is ConnectionMode.WIFI
                    else "No device is connected yet."
                )
            case DeviceConnectionState.UNAUTHORIZED:
                serial = connection.serial or "The device"
                return (
                    f"{serial} was found, but authorization still needs to be accepted on the device."
                    if self.connection_mode is ConnectionMode.USB
                    else f"{serial} was found over Wi-Fi, but authorization still needs to be accepted on the device."
                )
            case DeviceConnectionState.OFFLINE:
                serial = connection.serial or "The device"
                return (
                    f"{serial} is visible to ADB, but the connection is offline."
                    if self.connection_mode is ConnectionMode.USB
                    else f"{serial} is visible to ADB over Wi-Fi, but the connection is offline."
                )
            case DeviceConnectionState.ERROR:
                return connection.detail or "ADB returned an unexpected result."
            case DeviceConnectionState.READY:
                serial = connection.serial or "The device"
                return (
                    f"{serial} is ready."
                    if self.connection_mode is ConnectionMode.USB
                    else f"{serial} is ready over Wi-Fi."
                )

    def _connection_tone(self, connection: DeviceConnection) -> str:
        match connection.state:
            case DeviceConnectionState.READY:
                return "ready"
            case DeviceConnectionState.NO_DEVICE:
                return "error"
            case DeviceConnectionState.UNAUTHORIZED | DeviceConnectionState.OFFLINE | DeviceConnectionState.ERROR:
                return "error"

    def _on_platform_tools_progress(self, message: str) -> None:
        self.activity_panel.append_message(message)

    def _describe_adb_status(self, result) -> str:
        if result.success:
            first_line = next((line for line in result.stdout.splitlines() if line.strip()), "ADB is available.")
            return first_line
        return result.describe()

    def _set_system_status(self, message: str, *, tone: str = "info", tooltip: str | None = None) -> None:
        self._apply_status_value("system", message, tone, tooltip, self.status_panel.set_system_status)

    def _set_adb_status(self, message: str, *, tone: str = "info", tooltip: str | None = None) -> None:
        self._apply_status_value("adb", message, tone, tooltip, self.status_panel.set_adb_status)

    def _set_connection_status(self, message: str, *, tone: str = "info", tooltip: str | None = None) -> None:
        self._apply_status_value("connection", message, tone, tooltip, self.status_panel.set_connection_status)

    def _set_capture_status(self, message: str, *, tone: str = "warn", tooltip: str | None = None) -> None:
        self._apply_status_value("capture", message, tone, tooltip, self.status_panel.set_capture_status)

    def _apply_status_value(
        self,
        key: str,
        message: str,
        tone: str,
        tooltip: str | None,
        setter,
    ) -> None:
        state = (message, tone, tooltip)
        if self._last_status_values.get(key) == state:
            self._debug_log(f"GUI skipped status update: {key} -> {message} ({tone})")
            return
        self._last_status_values[key] = state
        self._debug_log(f"GUI applied status update: {key} -> {message} ({tone})")
        setter(message, tone=tone, tooltip=tooltip)

    def _show_guidance(self, connection: DeviceConnection) -> None:
        state = ("guidance", (self.connection_mode.value, connection.state.value, connection.serial, connection.detail))
        if self._last_central_panel_state == state:
            self._debug_log("GUI skipped central panel guidance update.")
            return
        self._last_central_panel_state = state
        self._debug_log("GUI applied central panel guidance update.")
        self.central_panel.show_guidance(connection)

    def _show_device_info(self, info: DeviceInfo) -> None:
        state = (
            "device_info",
            (
                self.connection_mode.value,
                info.model,
                info.manufacturer,
                info.android_version,
                info.device_name,
                info.serial_number,
                info.build_id,
                info.fingerprint,
            ),
        )
        if self._last_central_panel_state == state:
            self._debug_log("GUI skipped central panel device-info update.")
            return
        self._last_central_panel_state = state
        self._debug_log("GUI applied central panel device-info update.")
        self.central_panel.show_device_info(info)

    def _show_ready_without_info(self, serial: str, message: str) -> None:
        state = ("ready_without_info", (self.connection_mode.value, serial, message))
        if self._last_central_panel_state == state:
            self._debug_log("GUI skipped central panel ready-without-info update.")
            return
        self._last_central_panel_state = state
        self._debug_log("GUI applied central panel ready-without-info update.")
        self.central_panel.show_ready_without_info(serial, message)

    def _show_capture_state(self, serial: str, log_path: str, message: str) -> None:
        state = ("capture", (serial, log_path, message))
        if self._last_central_panel_state == state:
            self._debug_log("GUI skipped central panel capture-state update.")
            return
        self._last_central_panel_state = state
        self._debug_log("GUI applied central panel capture-state update.")
        self.central_panel.show_capture_state(serial, log_path, message)

    def _set_capture_controls(
        self,
        *,
        ready_device: bool,
        capture_running: bool,
        export_ready: bool,
        device_selection_enabled: bool,
    ) -> None:
        state = (ready_device, capture_running, export_ready, device_selection_enabled)
        if self._last_capture_controls_state == state:
            self._debug_log("GUI skipped capture-controls update.")
            return
        self._last_capture_controls_state = state
        self._debug_log("GUI applied capture-controls update.")
        self.action_bar.set_capture_controls(
            ready_device=ready_device,
            capture_running=capture_running,
            export_ready=export_ready,
            device_selection_enabled=device_selection_enabled,
        )

    def _set_wireless_action_state(
        self,
        *,
        has_device: bool,
        pairing_enabled: bool,
        disconnect_enabled: bool,
    ) -> None:
        state = (has_device, pairing_enabled, disconnect_enabled)
        if self._last_wireless_action_state == state:
            self._debug_log("GUI skipped wireless action-state update.")
            return
        self._last_wireless_action_state = state
        self._debug_log("GUI applied wireless action-state update.")
        self.central_panel.set_wireless_action_state(
            has_device=has_device,
            pairing_enabled=pairing_enabled,
            disconnect_enabled=disconnect_enabled,
        )

    def _set_wireless_setup_controls_enabled(self, enabled: bool) -> None:
        if self.wireless_setup_window is None:
            return
        if self._last_wireless_setup_enabled == enabled:
            self._debug_log(f"GUI skipped wireless setup enabled update: {enabled}")
            return
        self._last_wireless_setup_enabled = enabled
        self._debug_log(f"GUI applied wireless setup enabled update: {enabled}")
        self.wireless_setup_window.set_controls_enabled(enabled)

    def _set_activity_summary(
        self,
        message: str,
        tone: str,
        *,
        popup: bool = False,
        popup_title: str | None = None,
    ) -> None:
        state = (message, tone)
        if self._last_activity_summary_state == state:
            self._debug_log(f"GUI skipped activity summary update: {message} ({tone})")
        else:
            self._last_activity_summary_state = state
            self._debug_log(f"GUI applied activity summary update: {message} ({tone})")
            self.activity_panel.set_summary_state(message, tone)
        if popup and tone in {"warn", "error"}:
            self._show_feedback_popup(
                title=popup_title or ("Warning" if tone == "warn" else "Error"),
                message=message,
                tone=tone,
            )

    def _show_feedback_popup(self, *, title: str, message: str, tone: str) -> None:
        dialog = self._build_message_box(title=title, message=message, tone=tone)
        dialog.addButton(QMessageBox.StandardButton.Ok)
        dialog.exec()

    def _show_capture_complete_popup(self) -> None:
        dialog = self._build_message_box(
            title="Capture Complete",
            message="Log capture stopped and the file is ready for export.",
            tone="warn",
        )
        export_button = dialog.addButton("Export", QMessageBox.ButtonRole.AcceptRole)
        dialog.addButton(QMessageBox.StandardButton.Ok)
        dialog.exec()
        if dialog.clickedButton() is export_button:
            if self.latest_log_path is not None and self.latest_log_path.exists():
                self._begin_export_for_log(self.latest_log_path)

    def _build_message_box(self, *, title: str, message: str, tone: str) -> QMessageBox:
        dialog = QMessageBox(self)
        dialog.setWindowTitle(title)
        dialog.setText(message)
        dialog.setIcon(QMessageBox.Icon.Critical if tone == "error" else QMessageBox.Icon.Warning)
        dialog.setStyleSheet(
            self.styleSheet()
            + """
            QMessageBox {
                background: #161b22;
            }
            QMessageBox QLabel {
                color: #e6edf3;
                min-width: 320px;
            }
            """
        )
        for label in dialog.findChildren(QLabel):
            label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            label.setWordWrap(True)
        return dialog

    def _list_available_capture_logs(self) -> list[Path]:
        captures_root = get_captures_root()
        if not captures_root.exists():
            return []
        return sorted(
            (path for path in captures_root.rglob("logcat.txt") if path.is_file()),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )

    def _open_export_picker(self, log_paths: list[Path]) -> None:
        if self.export_picker_window is None:
            self.export_picker_window = ExportPickerWindow(self)
            self.export_picker_window.setStyleSheet(self.styleSheet())
            self.export_picker_window.log_selected.connect(self._on_export_log_selected)
        self.export_picker_window.set_logs(log_paths)
        self.export_picker_window.show()
        self.export_picker_window.raise_()
        self.export_picker_window.activateWindow()

    def _on_export_log_selected(self, log_path: str) -> None:
        self._begin_export_for_log(Path(log_path))

    def _begin_export_for_log(self, log_path: Path) -> None:
        suggested_serial = (
            self.current_device_info.serial_number
            if self.current_device_info is not None and self.current_device_info.serial_number
            else (self.current_connection.serial or log_path.parent.name or "device")
        )
        suggested_name = f"lazy-adb-support-{suggested_serial}.zip".replace(":", "_")
        destination, _ = QFileDialog.getSaveFileName(
            self,
            "Export Support Package",
            str(Path.home() / suggested_name),
            "Zip Archives (*.zip)",
        )
        if not destination:
            return
        self._debug_log(f"Starting export package flow to {destination} using log {log_path}.")
        self.activity_panel.append_message(f"Creating support package at {destination}.")
        self._start_background_task(
            action="export",
            label="Export Package",
            connection=self.current_connection,
            device_info=self.current_device_info,
            log_path=log_path,
            adb_version_output=self.latest_adb_version_output,
            destination_path=Path(destination),
        )

    def _enable_debug_logging(self) -> None:
        log_root = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[1]
        log_path = log_root / "lazy-adb-debug.log"
        logger = logging.getLogger("lazy_adb_debug")
        logger.setLevel(logging.INFO)
        logger.propagate = False
        handler = logging.FileHandler(log_path, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
        logger.handlers.clear()
        logger.addHandler(handler)
        self._debug_logger = logger
        self._debug_log_handler = handler
        self._debug_log_enabled = True
        self._debug_log(f"Debug logging enabled at {log_path}.")

    def _disable_debug_logging(self) -> None:
        if not self._debug_log_enabled:
            return
        self._debug_log("Debug logging disabled.")
        if self._debug_logger is not None and self._debug_log_handler is not None:
            self._debug_logger.removeHandler(self._debug_log_handler)
            self._debug_log_handler.close()
        self._debug_logger = None
        self._debug_log_handler = None
        self._debug_log_enabled = False

    def _debug_log(self, message: str) -> None:
        if self._debug_log_enabled and self._debug_logger is not None:
            self._debug_logger.info(message)

    def _apply_window_sizing(self) -> None:
        target_size = self.sizeHint().expandedTo(QSize(1380, 940))
        self.resize(target_size)
        self.setMinimumSize(target_size)
        self._update_content_layout_mode()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._update_content_layout_mode()

    def _poll_capture_log(self) -> None:
        self._flush_capture_log(final=False)

    def _flush_capture_log(self, *, final: bool) -> None:
        if self.latest_log_path is None or not self.latest_log_path.exists():
            return

        with self.latest_log_path.open("r", encoding="utf-8", errors="replace") as handle:
            handle.seek(self._capture_log_offset)
            chunk = handle.read()
            self._capture_log_offset = handle.tell()

        if not chunk and not final:
            return

        combined = self._capture_partial_line + chunk
        self._capture_partial_line = ""
        lines = combined.splitlines(keepends=True)
        for line in lines:
            if line.endswith("\n") or final:
                self.activity_panel.append_stream_line(line.rstrip("\n"))
            else:
                self._capture_partial_line = line

        if final and self._capture_partial_line:
            self.activity_panel.append_stream_line(self._capture_partial_line)
            self._capture_partial_line = ""

    def _sync_action_state(self) -> None:
        busy = self._is_busy()
        ready_device = self.current_connection.state is DeviceConnectionState.READY and not busy
        capture_running = self.capture_manager.active_session is not None
        export_ready = self.current_device_info is not None or self.latest_log_path is not None
        self.usb_mode_button.setEnabled(not capture_running and not busy)
        self.wifi_mode_button.setEnabled(not capture_running and not busy)
        self._sync_mode_buttons()
        wireless_ready = not capture_running and not self._platform_tools_bootstrap_failed and not busy
        self._set_wireless_action_state(
            has_device=self.connection_mode is ConnectionMode.WIFI and bool(self._available_devices),
            pairing_enabled=self.connection_mode is ConnectionMode.WIFI and wireless_ready,
            disconnect_enabled=(
                self.connection_mode is ConnectionMode.WIFI
                and wireless_ready
                and self.current_connection.serial is not None
            ),
        )
        self._set_wireless_setup_controls_enabled(wireless_ready)
        self._sync_advanced_target()
        self._set_device_choices(
            choices=[(self._format_device_choice(device), device.serial) for device in self._available_devices],
            selected_serial=self._preferred_device_serial,
            enabled=not capture_running and not busy,
        )
        self._set_capture_controls(
            ready_device=ready_device,
            capture_running=capture_running,
            export_ready=export_ready,
            device_selection_enabled=not capture_running and not busy,
        )

    def _format_device_choice(self, device: ListedDevice) -> str:
        state_label = {
            "device": "Ready",
            "unauthorized": "Unauthorized",
            "offline": "Offline",
        }.get(device.raw_state, device.raw_state.replace("_", " ").title())
        return f"{device.serial} · {state_label}"

    def _sync_advanced_target(self) -> None:
        if self.advanced_window is None:
            return
        if (
            self.current_connection.state is DeviceConnectionState.READY
            and self.current_connection.serial
            and not self._is_busy()
        ):
            hardware_serial = self.current_device_info.serial_number if self.current_device_info is not None else "Pending refresh"
            state = (f"Target: {hardware_serial} via {self.current_connection.serial}", True)
            if self._last_advanced_target_state == state:
                self._debug_log("GUI skipped advanced target update.")
                return
            self._last_advanced_target_state = state
            self._debug_log("GUI applied advanced target update.")
            self.advanced_window.set_target(*state)
            return
        state = (
            "Target: Background task in progress." if self._is_busy() else "Target: No ready device selected.",
            False,
        )
        if self._last_advanced_target_state == state:
            self._debug_log("GUI skipped advanced target update.")
            return
        self._last_advanced_target_state = state
        self._debug_log("GUI applied advanced target update.")
        self.advanced_window.set_target(*state)

    def _describe_command_feedback(self, result) -> str:
        if result.success:
            first_line = next((line.strip() for line in result.stdout.splitlines() if line.strip()), "")
            if first_line:
                return first_line
        return result.describe()

    def _sync_mode_buttons(self) -> None:
        self.usb_mode_button.blockSignals(True)
        self.wifi_mode_button.blockSignals(True)
        self.usb_mode_button.setChecked(self.connection_mode is ConnectionMode.USB)
        self.wifi_mode_button.setChecked(self.connection_mode is ConnectionMode.WIFI)
        self.usb_mode_button.blockSignals(False)
        self.wifi_mode_button.blockSignals(False)

    def _is_busy(self) -> bool:
        return self._command_in_progress or self._background_task_in_progress

    def _update_content_layout_mode(self) -> None:
        available_height = max(0, self.height() - 220)
        central_height_hint = self.central_panel.sizeHint().height()
        should_use_side_by_side = available_height < central_height_hint + 220
        if should_use_side_by_side == self._content_side_by_side:
            return

        self._content_side_by_side = should_use_side_by_side
        if should_use_side_by_side:
            self.content_layout.setDirection(QBoxLayout.LeftToRight)
            self.content_layout.setStretch(0, 3)
            self.content_layout.setStretch(1, 2)
            self.activity_panel.setMinimumWidth(420)
            self.activity_panel.setMinimumHeight(0)
        else:
            self.content_layout.setDirection(QBoxLayout.TopToBottom)
            self.content_layout.setStretch(0, 3)
            self.content_layout.setStretch(1, 2)
            self.activity_panel.setMinimumWidth(0)
            self.activity_panel.setMinimumHeight(180)

    def _set_device_choices(
        self,
        *,
        choices: list[tuple[str, str]],
        selected_serial: str | None,
        enabled: bool,
    ) -> None:
        state = (self.connection_mode, tuple(choices), selected_serial, enabled)
        if self._last_device_choice_state == state:
            self._debug_log("GUI skipped device-choice update.")
            return
        self._last_device_choice_state = state
        self._debug_log("GUI applied device-choice update.")
        if self.connection_mode is ConnectionMode.WIFI:
            self.action_bar.set_device_choices(choices=[], selected_serial=None, enabled=False)
            self.central_panel.set_wireless_device_choices(
                choices=choices,
                selected_serial=selected_serial,
                enabled=enabled,
            )
            return
        self.central_panel.set_wireless_device_choices(choices=[], selected_serial=None, enabled=False)
        self.action_bar.set_device_choices(
            choices=choices,
            selected_serial=selected_serial,
            enabled=enabled,
        )

    def closeEvent(self, event: QCloseEvent) -> None:
        self.status_timer.stop()
        self.capture_tail_timer.stop()
        for window in [self.wireless_setup_window, self.guide_window, self.advanced_window, self.export_picker_window]:
            if window is not None:
                window.close()
        if self.capture_manager.active_session is not None:
            result = self.capture_manager.stop_capture()
            self.latest_log_path = result.log_path or self.latest_log_path
        self._flush_capture_log(final=True)
        self._wait_for_thread(self._status_refresh_thread, timeout_ms=9000)
        self._wait_for_thread(self._action_thread, timeout_ms=25000)
        self._wait_for_thread(self._background_task_thread, timeout_ms=25000)
        self._debug_log("Application closing. Sending adb kill-server.")
        self.adb_manager.kill_server()
        self._disable_debug_logging()
        super().closeEvent(event)

    def _wait_for_thread(self, thread: QThread | None, *, timeout_ms: int) -> None:
        if thread is None or not thread.isRunning():
            return
        self._debug_log(f"Waiting for thread shutdown: {thread.objectName() or '<unnamed>'}")
        thread.wait(timeout_ms)
