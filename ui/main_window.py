from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shlex

from PySide6.QtCore import QObject, QSize, QThread, QTimer, Signal
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QMainWindow, QMessageBox, QPushButton, QVBoxLayout, QWidget

from core.adb_manager import ADBManager, CommandResult, DeviceDiscovery, DeviceInfoResult
from core.device_info import DeviceInfo
from core.device_state import ConnectionMode, DeviceConnection, DeviceConnectionState, ListedDevice, filter_devices_for_mode
from core.exporter import SupportPackageExporter
from core.log_capture import LogCaptureManager
from core.platform_tools_bootstrap import PlatformToolsBootstrapper
from ui.action_bar import ActionBar
from ui.advanced_window import AdvancedWindow
from ui.activity_panel import ActivityPanel
from ui.central_panel import CentralPanel
from ui.guide_window import GuideWindow
from ui.status_panel import StatusPanel
from ui.wireless_setup_window import WirelessSetupWindow
from utils.platform_paths import describe_host_system


@dataclass(slots=True)
class RuntimeStateSnapshot:
    adb_result: CommandResult | None
    discovery: DeviceDiscovery
    device_info_result: DeviceInfoResult | None


class RuntimeStateWorker(QObject):
    finished = Signal(object, bool, int)
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
            self.finished.emit(
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
        self._adb_version_checked = False
        self._status_refresh_thread: QThread | None = None
        self._status_refresh_worker: RuntimeStateWorker | None = None
        self._status_refresh_in_progress = False
        self._queued_refresh: tuple[bool, bool] | None = None
        self._refresh_generation = 0

        self.setWindowTitle("Lazy ADB Wizard")

        self.action_bar = ActionBar()
        self.central_panel = CentralPanel()
        self.status_panel = StatusPanel()
        self.activity_panel = ActivityPanel()
        self.guide_window: GuideWindow | None = None
        self.wireless_setup_window: WirelessSetupWindow | None = None
        self.advanced_window: AdvancedWindow | None = None
        self.usb_mode_button = QPushButton("USB")
        self.wifi_mode_button = QPushButton("Wi-Fi")
        self.status_timer = QTimer(self)
        self.status_timer.setInterval(4000)
        self.capture_tail_timer = QTimer(self)
        self.capture_tail_timer.setInterval(400)

        self._build_layout()
        self._apply_styles()
        self._connect_signals()
        self.status_panel.set_system_status(describe_host_system(), tone="info")
        self.status_panel.set_capture_status("Idle", tone="warn")
        self.activity_panel.setMinimumHeight(180)
        self.central_panel.set_mode(self.connection_mode)
        self.central_panel.show_guidance(self.current_connection)
        self._sync_action_state()
        self._apply_window_sizing()
        QTimer.singleShot(0, self._startup_refresh)

    def _build_layout(self) -> None:
        title = QLabel("Lazy ADB Wizard")
        title.setObjectName("HeaderTitle")

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
        header_layout.addWidget(title)
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
        layout.addWidget(self.central_panel, stretch=3)
        layout.addWidget(self.activity_panel, stretch=2)
        self.setCentralWidget(root)

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow {
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
            QLineEdit:focus, QComboBox:focus {
                border-color: #58a6ff;
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
        self.status_timer.timeout.connect(self.on_poll_status)
        self.capture_tail_timer.timeout.connect(self._poll_capture_log)

    def on_check_connection(self) -> None:
        if not self._ensure_platform_tools_available(log_changes=True, allow_retry=True):
            return
        self._refresh_runtime_state(log_changes=True, force_device_refresh=True)
        if self.current_connection.state is not DeviceConnectionState.READY:
            self._show_feedback_popup(
                title="Connection Status",
                message=self._friendly_state_summary(self.current_connection),
                tone="warn",
            )

    def on_refresh_device_info(self) -> None:
        if self.current_connection.state is not DeviceConnectionState.READY or not self.current_connection.serial:
            self._set_activity_summary("No ready device is selected yet.", "warn", popup=True, popup_title="Refresh Device Info")
            self.activity_panel.append_message("Check the connection first so the application can choose a device.")
            return

        self._apply_device_info_result(
            self.adb_manager.read_device_info(self.current_connection.serial),
            announce_success=True,
        )
        self.status_panel.set_connection_status(
            "Connected" if self.current_connection.state is DeviceConnectionState.READY else "Disconnected",
            tone=self._connection_tone(self.current_connection),
            tooltip=self._friendly_state_summary(self.current_connection),
        )
        self._sync_advanced_target()

    def on_device_selected(self, serial: str) -> None:
        if serial == self._preferred_device_serial:
            return

        self._preferred_device_serial = serial
        self.activity_panel.append_message(f"Switched active target to {serial}.")
        self._refresh_runtime_state(log_changes=True, force_device_refresh=True)
        self._sync_advanced_target()

    def on_open_guide(self) -> None:
        if self.guide_window is None:
            self.guide_window = GuideWindow(self)
            self.guide_window.setStyleSheet(self.styleSheet())
        self.guide_window.show_for_mode(self.connection_mode)

    def on_open_wireless_setup(self) -> None:
        self._wireless_setup_auto_opened = True
        if self.wireless_setup_window is None:
            self.wireless_setup_window = WirelessSetupWindow(self)
            self.wireless_setup_window.setStyleSheet(self.styleSheet())
            self.wireless_setup_window.pair_requested.connect(self.on_pair_wireless)
            self.wireless_setup_window.connect_requested.connect(self.on_connect_wireless)
        self.wireless_setup_window.set_controls_enabled(
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
        if self.capture_manager.active_session is not None or mode is self.connection_mode:
            self._sync_mode_buttons()
            return

        self.connection_mode = mode
        self._refresh_generation += 1
        self._wireless_setup_auto_opened = False
        self._preferred_device_serial = None
        self._available_devices = []
        self.current_device_info = None
        self.current_connection = DeviceConnection(state=DeviceConnectionState.NO_DEVICE)
        self._adb_version_checked = False
        self._set_device_choices(choices=[], selected_serial=None, enabled=False)
        self.central_panel.set_mode(mode)
        self.central_panel.show_guidance(self.current_connection)
        self._set_activity_summary(
            "Wireless ADB mode is active. Pair or connect a device from the main panel."
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
            return
        if not host or not port or not pairing_code:
            self._set_activity_summary(
                "Wireless pairing needs host, pairing port, and pairing code.",
                "warn",
                popup=True,
                popup_title="Wireless Pairing",
            )
            return
        if not port.isdigit():
            self._set_activity_summary("The pairing port must be numeric.", "warn", popup=True, popup_title="Wireless Pairing")
            return
        if not self._ensure_platform_tools_available(log_changes=True, allow_retry=True):
            return

        self.activity_panel.append_message(f"Pairing with {host}:{port}.")
        result = self.adb_manager.pair_device(host, port, pairing_code)
        self.activity_panel.append_message(self._describe_command_feedback(result))
        if result.success:
            self._set_activity_summary("Wireless pairing succeeded. Connect using the device's debug port.", "ready")
        else:
            self._set_activity_summary("Wireless pairing failed.", "error")
            self._show_feedback_popup(title="Wireless Pairing", message=result.describe(), tone="error")

    def on_connect_wireless(self, host: str, port: str) -> None:
        if self.connection_mode is not ConnectionMode.WIFI:
            return
        if not host or not port:
            self._set_activity_summary("Wireless connect needs a host and connect port.", "warn", popup=True, popup_title="Wireless Connect")
            return
        if not port.isdigit():
            self._set_activity_summary("The connect port must be numeric.", "warn", popup=True, popup_title="Wireless Connect")
            return
        if not self._ensure_platform_tools_available(log_changes=True, allow_retry=True):
            return

        endpoint = f"{host}:{port}"
        self.activity_panel.append_message(f"Connecting to {endpoint}.")
        result = self.adb_manager.connect_device(host, port)
        self.activity_panel.append_message(self._describe_command_feedback(result))
        if not result.success:
            self._set_activity_summary("Wireless connection failed.", "error")
            self._show_feedback_popup(title="Wireless Connect", message=result.describe(), tone="error")
            return

        self._preferred_device_serial = endpoint
        self._set_activity_summary("Wireless connection succeeded.", "ready")
        self._refresh_runtime_state(log_changes=True, force_device_refresh=True)

    def on_disconnect_wireless(self, target: str) -> None:
        if self.connection_mode is not ConnectionMode.WIFI:
            return

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

        self.activity_panel.append_message(f"Disconnecting {endpoint}.")
        result = self.adb_manager.disconnect_device(endpoint)
        self.activity_panel.append_message(self._describe_command_feedback(result))
        if result.success:
            if self._preferred_device_serial == endpoint:
                self._preferred_device_serial = None
            self._set_activity_summary("Wireless device disconnected.", "warn", popup=True, popup_title="Wireless Disconnect")
        else:
            self._set_activity_summary("Wireless disconnect failed.", "error")
            self._show_feedback_popup(title="Wireless Disconnect", message=result.describe(), tone="error")
        self._refresh_runtime_state(log_changes=True, force_device_refresh=True)

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

        result = self.adb_manager.run(args, serial=self.current_connection.serial, timeout=30.0)
        command_preview = " ".join(args)
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
            self._show_feedback_popup(title="Advanced", message=result.describe(), tone="error")

    def on_start_capture(self) -> None:
        if self.current_connection.state is not DeviceConnectionState.READY or not self.current_connection.serial:
            self._set_activity_summary("No ready device is available for capture.", "warn", popup=True, popup_title="Start Capture")
            self.activity_panel.append_message("Connect and authorize a device before starting logcat capture.")
            return

        result = self.capture_manager.start_capture(self.current_connection.serial)
        if not result.success or result.session is None:
            self._set_activity_summary("Log capture could not be started.", "error")
            self.activity_panel.append_message(result.message)
            self._show_feedback_popup(title="Start Capture", message=result.message, tone="error")
            return

        self.central_panel.show_capture_state(
            result.session.serial,
            str(result.session.log_path),
            "Logcat is being written live to disk. Reproduce the issue, then stop the capture.",
        )
        self._set_activity_summary("Log capture is running.", "ready")
        self.activity_panel.append_message(result.message)
        self.latest_log_path = result.session.log_path
        self._capture_log_offset = 0
        self._capture_partial_line = ""
        self.capture_tail_timer.start()
        self.status_panel.set_capture_status(f"Capturing to {result.session.log_path.name}", tone="ready")
        self._sync_action_state()

    def on_stop_capture(self) -> None:
        result = self.capture_manager.stop_capture()
        self._flush_capture_log(final=True)
        self.capture_tail_timer.stop()
        if not result.success:
            self._set_activity_summary("Log capture could not be stopped cleanly.", "error")
            self.activity_panel.append_message(result.message)
            if result.stderr.strip():
                self.activity_panel.append_message(result.stderr.strip())
            self._show_feedback_popup(title="Stop Capture", message=result.message, tone="error")
            self.status_panel.set_capture_status("Capture stopped with issues", tone="error")
            self._sync_action_state()
            return

        self.activity_panel.clear_feed()
        self.latest_log_path = result.log_path or self.latest_log_path
        if self.current_device_info is not None:
            self.central_panel.show_device_info(self.current_device_info)
        elif self.current_connection.serial:
            self.central_panel.show_ready_without_info(
                self.current_connection.serial,
                "Capture finished. Refresh device information if you want the latest details in the export package.",
            )
        else:
            self.central_panel.show_guidance(self.current_connection)

        self._set_activity_summary("Log capture stopped and the file is ready for export.", "warn", popup=True, popup_title="Capture Complete")
        self.activity_panel.append_message(result.message)
        if result.stderr.strip():
            self.activity_panel.append_message(result.stderr.strip())
        self.status_panel.set_capture_status("Idle", tone="warn")
        self._sync_action_state()

    def on_export_package(self) -> None:
        result = self.exporter.create_package(
            connection=self.current_connection,
            device_info=self.current_device_info,
            log_path=self.latest_log_path,
            adb_version_output=self.latest_adb_version_output,
        )
        if result.success:
            self._set_activity_summary("Support package created successfully.", "ready")
            self.activity_panel.append_message(result.message)
        else:
            self._set_activity_summary("Support package could not be created.", "error")
            self.activity_panel.append_message(result.message)
            self._show_feedback_popup(title="Export Package", message=result.message, tone="error")
        self._sync_action_state()

    def on_poll_status(self) -> None:
        self._refresh_runtime_state(log_changes=False, force_device_refresh=False)

    def _startup_refresh(self) -> None:
        self._ensure_platform_tools_available(log_changes=True, allow_retry=True)
        self._refresh_runtime_state(log_changes=True, force_device_refresh=True)
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
            self.central_panel.set_wireless_action_state(
                has_device=False,
                pairing_enabled=False,
                disconnect_enabled=False,
            )
            self.status_panel.set_adb_status(
                "Inactive",
                tone="error",
                tooltip="Bundled platform-tools are still missing.",
            )
            return False

        self._set_activity_summary("Bundled platform-tools are missing. Downloading the package for this system.", "warn")
        self.central_panel.set_wireless_action_state(
            has_device=False,
            pairing_enabled=False,
            disconnect_enabled=False,
        )
        self.status_panel.set_adb_status("Inactive", tone="error", tooltip="Downloading platform-tools...")
        self.status_panel.set_connection_status(
            "Disconnected",
            tone="error",
            tooltip="Waiting for platform-tools download.",
        )

        if log_changes:
            self.activity_panel.append_message("Bundled platform-tools are not present. Starting first-run download.")

        QApplication.processEvents()
        result = self.platform_tools_bootstrapper.ensure_present(progress_cb=self._on_platform_tools_progress)
        QApplication.processEvents()

        if result.success:
            self._platform_tools_bootstrap_failed = False
            if result.downloaded:
                self.activity_panel.append_message(result.message)
            self._set_activity_summary("Platform-tools are ready.", "ready")
            self.central_panel.set_wireless_action_state(
                has_device=bool(self._available_devices),
                pairing_enabled=self.capture_manager.active_session is None,
                disconnect_enabled=self.capture_manager.active_session is None and self.current_connection.serial is not None,
            )
            self.status_panel.set_adb_status(
                "Active",
                tone="ready",
                tooltip="Bundled platform-tools are installed.",
            )
            return True

        self._platform_tools_bootstrap_failed = True
        self._available_devices = []
        self._preferred_device_serial = None
        self._adb_version_checked = False
        self._set_device_choices(choices=[], selected_serial=None, enabled=False)
        self.central_panel.set_wireless_action_state(
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
        self.status_panel.set_adb_status("Inactive", tone="error", tooltip="Platform-tools download failed.")
        self.status_panel.set_connection_status(
            "Disconnected",
            tone="error",
            tooltip="ADB is unavailable until platform-tools are installed.",
        )
        self.central_panel.show_guidance(self.current_connection)
        return False

    def _refresh_runtime_state(self, *, log_changes: bool, force_device_refresh: bool) -> None:
        if not self._ensure_platform_tools_available(log_changes=log_changes, allow_retry=False):
            self._sync_action_state()
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

        self._start_runtime_state_worker(log_changes=log_changes, force_device_refresh=force_device_refresh)

    def _start_runtime_state_worker(self, *, log_changes: bool, force_device_refresh: bool) -> None:
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
        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(self._on_runtime_state_ready)
        worker.failed.connect(self._on_runtime_state_failed)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        worker.failed.connect(thread.quit)
        worker.failed.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._clear_runtime_state_worker)
        self._status_refresh_worker = worker
        self._status_refresh_thread = thread
        thread.start()

    def _on_runtime_state_ready(self, snapshot: RuntimeStateSnapshot, log_changes: bool, generation: int) -> None:
        if generation != self._refresh_generation:
            self._complete_runtime_state_refresh()
            return
        adb_result = snapshot.adb_result
        if adb_result is not None:
            adb_status = self._describe_adb_status(adb_result)
            self.status_panel.set_adb_status(
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
            self.status_panel.set_adb_status("Active", tone="ready", tooltip=adb_status)
        else:
            adb_status = snapshot.discovery.command_result.describe()
            self.status_panel.set_adb_status("Inactive", tone="error", tooltip=adb_status)
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
            self.central_panel.set_wireless_action_state(
                has_device=False,
                pairing_enabled=False,
                disconnect_enabled=False,
            )
            self.current_connection = DeviceConnection(
                state=DeviceConnectionState.ERROR,
                detail=snapshot.discovery.command_result.describe(),
            )
            self.current_device_info = None
            self.status_panel.set_connection_status(
                "Disconnected",
                tone="error",
                tooltip=self._friendly_state_summary(self.current_connection),
            )
            if self.capture_manager.active_session is None:
                self.central_panel.show_guidance(self.current_connection)
            if log_changes:
                self._set_activity_summary("ADB is unavailable, so device detection could not continue.", "error")
            self._complete_runtime_state_refresh()
            return

        discovery = snapshot.discovery
        self._available_devices = filter_devices_for_mode(discovery.devices, self.connection_mode)
        if self.connection_mode is ConnectionMode.WIFI:
            if self._available_devices:
                self._wireless_setup_auto_opened = False
            elif not self._wireless_setup_auto_opened:
                self.on_open_wireless_setup()
        self.central_panel.set_wireless_action_state(
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
        if self.current_connection.serial is not None:
            self._preferred_device_serial = self.current_connection.serial
        elif not self._available_devices:
            self._preferred_device_serial = None

        self._set_device_choices(
            choices=[(self._format_device_choice(device), device.serial) for device in self._available_devices],
            selected_serial=self._preferred_device_serial,
            enabled=self.capture_manager.active_session is None,
        )
        self.status_panel.set_connection_status(
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
                self.central_panel.show_device_info(self.current_device_info)
            self._set_activity_summary("Device detection is active and up to date.", "ready")
        else:
            self.current_device_info = None
            if self.capture_manager.active_session is None:
                self.central_panel.show_guidance(self.current_connection)
            if connection_changed and log_changes:
                self.activity_panel.append_message(self._friendly_state_summary(self.current_connection))
            if self.current_connection.state is DeviceConnectionState.NO_DEVICE:
                self._set_activity_summary(
                    "No wireless device was detected. Use the pairing form if needed."
                    if self.connection_mode is ConnectionMode.WIFI
                    else "No ready device was detected. Follow the setup guidance if needed.",
                    "warn",
                )
            else:
                self._set_activity_summary(
                    self._friendly_state_summary(self.current_connection),
                    self._connection_tone(self.current_connection),
                )

        self._complete_runtime_state_refresh()

    def _on_runtime_state_failed(self, message: str, log_changes: bool, generation: int) -> None:
        if generation != self._refresh_generation:
            self._complete_runtime_state_refresh()
            return
        self._adb_version_checked = False
        self.current_connection = DeviceConnection(
            state=DeviceConnectionState.ERROR,
            detail=message,
        )
        self.status_panel.set_adb_status("Inactive", tone="error", tooltip=message)
        self.status_panel.set_connection_status("Disconnected", tone="error", tooltip=message)
        if self.capture_manager.active_session is None:
            self.central_panel.show_guidance(self.current_connection)
        if log_changes:
            self._set_activity_summary("Background device refresh failed.", "error")
            self.activity_panel.append_message(message)
        self._complete_runtime_state_refresh()

    def _clear_runtime_state_worker(self) -> None:
        self._status_refresh_thread = None
        self._status_refresh_worker = None

    def _complete_runtime_state_refresh(self) -> None:
        self._status_refresh_in_progress = False
        self._sync_action_state()
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
                self.central_panel.show_device_info(result.device_info)
            if announce_success:
                self.activity_panel.append_message("Device information loaded successfully.")
            self._set_activity_summary("Device information is up to date.", "ready")
            self.status_panel.set_connection_status(
                "Connected" if self.current_connection.state is DeviceConnectionState.READY else "Disconnected",
                tone=self._connection_tone(self.current_connection),
                tooltip=self._friendly_state_summary(self.current_connection),
            )
            self._sync_action_state()
            return

        self.current_device_info = None
        detail_message = result.command_result.describe()
        if self.current_connection.serial and self.capture_manager.active_session is None:
            self.central_panel.show_ready_without_info(
                self.current_connection.serial,
                detail_message,
            )
        self._set_activity_summary(
            "A target is connected, but it did not provide usable Android device information.",
            "error",
        )
        self.activity_panel.append_message(detail_message)
        self.status_panel.set_connection_status(
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
        QApplication.processEvents()

    def _describe_adb_status(self, result) -> str:
        if result.success:
            first_line = next((line for line in result.stdout.splitlines() if line.strip()), "ADB is available.")
            return first_line
        return result.describe()

    def _set_activity_summary(
        self,
        message: str,
        tone: str,
        *,
        popup: bool = False,
        popup_title: str | None = None,
    ) -> None:
        self.activity_panel.set_summary_state(message, tone)
        if popup and tone in {"warn", "error"}:
            self._show_feedback_popup(
                title=popup_title or ("Warning" if tone == "warn" else "Error"),
                message=message,
                tone=tone,
            )

    def _show_feedback_popup(self, *, title: str, message: str, tone: str) -> None:
        if tone == "error":
            QMessageBox.critical(self, title, message)
        else:
            QMessageBox.warning(self, title, message)

    def _apply_window_sizing(self) -> None:
        target_size = self.sizeHint().expandedTo(QSize(1380, 940))
        self.resize(target_size)
        self.setMinimumSize(target_size)

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
        ready_device = self.current_connection.state is DeviceConnectionState.READY
        capture_running = self.capture_manager.active_session is not None
        export_ready = self.current_device_info is not None or self.latest_log_path is not None
        self.usb_mode_button.setEnabled(not capture_running)
        self.wifi_mode_button.setEnabled(not capture_running)
        self._sync_mode_buttons()
        wireless_ready = not capture_running and not self._platform_tools_bootstrap_failed
        self.central_panel.set_wireless_action_state(
            has_device=self.connection_mode is ConnectionMode.WIFI and bool(self._available_devices),
            pairing_enabled=self.connection_mode is ConnectionMode.WIFI and wireless_ready,
            disconnect_enabled=(
                self.connection_mode is ConnectionMode.WIFI
                and wireless_ready
                and self.current_connection.serial is not None
            ),
        )
        if self.wireless_setup_window is not None:
            self.wireless_setup_window.set_controls_enabled(wireless_ready)
        self._sync_advanced_target()
        self._set_device_choices(
            choices=[(self._format_device_choice(device), device.serial) for device in self._available_devices],
            selected_serial=self._preferred_device_serial,
            enabled=not capture_running,
        )
        self.action_bar.set_capture_controls(
            ready_device=ready_device,
            capture_running=capture_running,
            export_ready=export_ready,
            device_selection_enabled=not capture_running,
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
        if self.current_connection.state is DeviceConnectionState.READY and self.current_connection.serial:
            hardware_serial = self.current_device_info.serial_number if self.current_device_info is not None else "Pending refresh"
            self.advanced_window.set_target(
                f"Target: {hardware_serial} via {self.current_connection.serial}",
                True,
            )
            return
        self.advanced_window.set_target("Target: No ready device selected.", False)

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

    def _set_device_choices(
        self,
        *,
        choices: list[tuple[str, str]],
        selected_serial: str | None,
        enabled: bool,
    ) -> None:
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
        if self.capture_manager.active_session is not None:
            result = self.capture_manager.stop_capture()
            self.latest_log_path = result.log_path or self.latest_log_path
        self._flush_capture_log(final=True)
        super().closeEvent(event)
