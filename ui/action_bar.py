from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QWidget


class ActionBar(QWidget):
    check_connection_requested = Signal()
    refresh_device_info_requested = Signal()
    start_capture_requested = Signal()
    stop_capture_requested = Signal()
    export_package_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self.check_connection_button = QPushButton("Check Connection")
        self.refresh_device_info_button = QPushButton("Refresh Device Info")
        self.start_capture_button = QPushButton("Start Capture")
        self.stop_capture_button = QPushButton("Stop Capture")
        self.export_package_button = QPushButton("Export Package")
        self.refresh_device_info_button.setEnabled(False)
        self.start_capture_button.setEnabled(False)
        self.stop_capture_button.setEnabled(False)
        self.export_package_button.setEnabled(False)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        layout.addWidget(self.check_connection_button)
        layout.addWidget(self.refresh_device_info_button)
        layout.addWidget(self.start_capture_button)
        layout.addWidget(self.stop_capture_button)
        layout.addWidget(self.export_package_button)
        layout.addStretch()

        self.check_connection_button.clicked.connect(self.check_connection_requested.emit)
        self.refresh_device_info_button.clicked.connect(self.refresh_device_info_requested.emit)
        self.start_capture_button.clicked.connect(self.start_capture_requested.emit)
        self.stop_capture_button.clicked.connect(self.stop_capture_requested.emit)
        self.export_package_button.clicked.connect(self.export_package_requested.emit)

    def set_capture_controls(self, *, ready_device: bool, capture_running: bool, export_ready: bool) -> None:
        self.refresh_device_info_button.setEnabled(ready_device and not capture_running)
        self.start_capture_button.setEnabled(ready_device and not capture_running)
        self.stop_capture_button.setEnabled(capture_running)
        self.export_package_button.setEnabled(export_ready and not capture_running)
