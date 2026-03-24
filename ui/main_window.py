from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QMainWindow, QVBoxLayout, QWidget

from core.adb_manager import ADBManager, DeviceInfoResult
from core.device_info import DeviceInfo
from core.device_state import DeviceConnection, DeviceConnectionState
from core.exporter import SupportPackageExporter
from core.log_capture import LogCaptureManager
from core.platform_tools_bootstrap import PlatformToolsBootstrapper
from ui.action_bar import ActionBar
from ui.activity_panel import ActivityPanel
from ui.central_panel import CentralPanel
from ui.status_panel import StatusPanel
from utils.platform_paths import describe_host_system


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()

        self.adb_manager = ADBManager()
        self.capture_manager = LogCaptureManager(self.adb_manager)
        self.exporter = SupportPackageExporter()
        self.platform_tools_bootstrapper = PlatformToolsBootstrapper()
        self.current_connection = DeviceConnection(state=DeviceConnectionState.NO_DEVICE)
        self.current_device_info: DeviceInfo | None = None
        self.latest_log_path: Path | None = None
        self.latest_adb_version_output = ""
        self._last_adb_status = ""
        self._last_connection_signature: tuple[str | None, str | None, str | None] | None = None
        self._capture_log_offset = 0
        self._capture_partial_line = ""
        self._platform_tools_bootstrap_failed = False

        self.setWindowTitle("Lazy ADB Wizard")
        self.resize(1280, 860)
        self.setMinimumSize(1180, 820)

        self.action_bar = ActionBar()
        self.central_panel = CentralPanel()
        self.status_panel = StatusPanel()
        self.activity_panel = ActivityPanel()
        self.status_timer = QTimer(self)
        self.status_timer.setInterval(2000)
        self.capture_tail_timer = QTimer(self)
        self.capture_tail_timer.setInterval(400)

        self._build_layout()
        self._apply_styles()
        self._connect_signals()
        self.status_panel.set_system_status(describe_host_system(), tone="info")
        self.status_panel.set_capture_status("Idle", tone="warn")
        self.activity_panel.setMinimumHeight(180)
        self.central_panel.show_guidance(self.current_connection)
        self._sync_action_state()
        QTimer.singleShot(0, self._startup_refresh)

    def _build_layout(self) -> None:
        title = QLabel("Lazy ADB Wizard")
        title.setObjectName("HeaderTitle")

        header_widget = QWidget()
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(16)
        header_layout.addWidget(title)
        self.status_panel.setMinimumWidth(520)
        self.status_panel.setMaximumWidth(900)
        header_layout.addWidget(self.status_panel)
        header_layout.addStretch()

        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)
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
        self.action_bar.check_connection_requested.connect(self.on_check_connection)
        self.action_bar.refresh_device_info_requested.connect(self.on_refresh_device_info)
        self.action_bar.start_capture_requested.connect(self.on_start_capture)
        self.action_bar.stop_capture_requested.connect(self.on_stop_capture)
        self.action_bar.export_package_requested.connect(self.on_export_package)
        self.status_timer.timeout.connect(self.on_poll_status)
        self.capture_tail_timer.timeout.connect(self._poll_capture_log)

    def on_check_connection(self) -> None:
        if not self._ensure_platform_tools_available(log_changes=True, allow_retry=True):
            return
        self._refresh_runtime_state(log_changes=True, force_device_refresh=True)

    def on_refresh_device_info(self) -> None:
        if self.current_connection.state is not DeviceConnectionState.READY or not self.current_connection.serial:
            self.activity_panel.set_summary("No ready device is selected yet.")
            self.activity_panel.set_summary_tone("warn")
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

    def on_start_capture(self) -> None:
        if self.current_connection.state is not DeviceConnectionState.READY or not self.current_connection.serial:
            self.activity_panel.set_summary("No ready device is available for capture.")
            self.activity_panel.set_summary_tone("warn")
            self.activity_panel.append_message("Connect and authorize a device before starting logcat capture.")
            return

        result = self.capture_manager.start_capture(self.current_connection.serial)
        if not result.success or result.session is None:
            self.activity_panel.set_summary("Log capture could not be started.")
            self.activity_panel.set_summary_tone("error")
            self.activity_panel.append_message(result.message)
            return

        self.central_panel.show_capture_state(
            result.session.serial,
            str(result.session.log_path),
            "Logcat is being written live to disk. Reproduce the issue, then stop the capture.",
        )
        self.activity_panel.set_summary("Log capture is running.")
        self.activity_panel.set_summary_tone("ready")
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
            self.activity_panel.set_summary("Log capture could not be stopped cleanly.")
            self.activity_panel.set_summary_tone("error")
            self.activity_panel.append_message(result.message)
            if result.stderr.strip():
                self.activity_panel.append_message(result.stderr.strip())
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

        self.activity_panel.set_summary("Log capture stopped and the file is ready for export.")
        self.activity_panel.set_summary_tone("warn")
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
            self.activity_panel.set_summary("Support package created successfully.")
            self.activity_panel.set_summary_tone("ready")
            self.activity_panel.append_message(result.message)
        else:
            self.activity_panel.set_summary("Support package could not be created.")
            self.activity_panel.set_summary_tone("error")
            self.activity_panel.append_message(result.message)
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
            self.status_panel.set_adb_status(
                "Inactive",
                tone="error",
                tooltip="Bundled platform-tools are still missing.",
            )
            return False

        self.activity_panel.set_summary("Bundled platform-tools are missing. Downloading the package for this system.")
        self.activity_panel.set_summary_tone("warn")
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
            self.activity_panel.set_summary("Platform-tools are ready.")
            self.activity_panel.set_summary_tone("ready")
            self.status_panel.set_adb_status(
                "Active",
                tone="ready",
                tooltip="Bundled platform-tools are installed.",
            )
            return True

        self._platform_tools_bootstrap_failed = True
        self.current_connection = DeviceConnection(
            state=DeviceConnectionState.ERROR,
            detail=result.message,
        )
        self.activity_panel.set_summary("Platform-tools download failed. Retry after restoring network access.")
        self.activity_panel.set_summary_tone("error")
        self.activity_panel.append_message(result.message)
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

        adb_result = self.adb_manager.get_version()
        adb_status = self._describe_adb_status(adb_result)
        self.status_panel.set_adb_status(
            "Active" if adb_result.success else "Inactive",
            tone="ready" if adb_result.success else "error",
            tooltip=adb_status,
        )
        if adb_result.success:
            self.latest_adb_version_output = adb_result.stdout

        adb_changed = adb_status != self._last_adb_status
        if adb_changed:
            self._last_adb_status = adb_status
            if log_changes:
                self.activity_panel.append_message(adb_status)

        if not adb_result.success:
            self.current_connection = DeviceConnection(
                state=DeviceConnectionState.ERROR,
                detail=adb_result.describe(),
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
                self.activity_panel.set_summary("ADB is unavailable, so device detection could not continue.")
                self.activity_panel.set_summary_tone("error")
            self._sync_action_state()
            return

        discovery = self.adb_manager.detect_devices()
        previous_signature = self._last_connection_signature
        current_signature = (
            discovery.connection.state.value,
            discovery.connection.serial,
            discovery.connection.detail,
        )
        connection_changed = current_signature != previous_signature
        self._last_connection_signature = current_signature
        self.current_connection = discovery.connection
        self.status_panel.set_connection_status(
            "Connected" if self.current_connection.state is DeviceConnectionState.READY else "Disconnected",
            tone=self._connection_tone(self.current_connection),
            tooltip=self._friendly_state_summary(self.current_connection),
        )

        if self.current_connection.state is DeviceConnectionState.READY and self.current_connection.serial:
            should_fetch_info = (
                force_device_refresh
                or self.current_device_info is None
                or previous_signature is None
                or previous_signature[1] != self.current_connection.serial
            )
            if connection_changed and log_changes:
                self.activity_panel.append_message(
                    f"Detected device {self.current_connection.serial} ({self.current_connection.raw_state})."
                )
            if should_fetch_info:
                self._apply_device_info_result(
                    self.adb_manager.read_device_info(self.current_connection.serial),
                    announce_success=log_changes,
                )
            elif self.capture_manager.active_session is None and self.current_device_info is not None:
                self.central_panel.show_device_info(self.current_device_info)
            self.activity_panel.set_summary("Device detection is active and up to date.")
            self.activity_panel.set_summary_tone("ready")
        else:
            self.current_device_info = None
            if self.capture_manager.active_session is None:
                self.central_panel.show_guidance(self.current_connection)
            if connection_changed and log_changes:
                self.activity_panel.append_message(self._friendly_state_summary(self.current_connection))
            if self.current_connection.state is DeviceConnectionState.NO_DEVICE:
                self.activity_panel.set_summary("No ready device was detected. Follow the setup guidance if needed.")
                self.activity_panel.set_summary_tone("warn")
            else:
                self.activity_panel.set_summary(self._friendly_state_summary(self.current_connection))
                self.activity_panel.set_summary_tone(self._connection_tone(self.current_connection))

        self._sync_action_state()

    def _apply_device_info_result(self, result: DeviceInfoResult, *, announce_success: bool) -> None:
        if result.device_info is not None:
            self.current_device_info = result.device_info
            if self.capture_manager.active_session is None:
                self.central_panel.show_device_info(result.device_info)
            if announce_success:
                self.activity_panel.append_message("Device information loaded successfully.")
            self.activity_panel.set_summary("Device information is up to date.")
            self.activity_panel.set_summary_tone("ready")
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
        self.activity_panel.set_summary("A target is connected, but it did not provide usable Android device information.")
        self.activity_panel.set_summary_tone("error")
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
                return "No device is connected yet."
            case DeviceConnectionState.UNAUTHORIZED:
                serial = connection.serial or "The device"
                return f"{serial} was found, but authorization still needs to be accepted on the device."
            case DeviceConnectionState.OFFLINE:
                serial = connection.serial or "The device"
                return f"{serial} is visible to ADB, but the connection is offline."
            case DeviceConnectionState.ERROR:
                return connection.detail or "ADB returned an unexpected result."
            case DeviceConnectionState.READY:
                serial = connection.serial or "The device"
                return f"{serial} is ready."

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
        self.action_bar.set_capture_controls(
            ready_device=ready_device,
            capture_running=capture_running,
            export_ready=export_ready,
        )

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.capture_manager.active_session is not None:
            result = self.capture_manager.stop_capture()
            self.latest_log_path = result.log_path or self.latest_log_path
        self._flush_capture_log(final=True)
        super().closeEvent(event)
