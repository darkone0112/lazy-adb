from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QPushButton, QWidget


class ActionBar(QWidget):
    check_connection_requested = Signal()
    device_selected = Signal(str)
    refresh_device_info_requested = Signal()
    start_capture_requested = Signal()
    stop_capture_requested = Signal()
    export_package_requested = Signal()
    open_guide_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self.check_connection_button = QPushButton("Check Connection")
        self.device_selector_label = QLabel("Device")
        self.device_selector = QComboBox()
        self.refresh_device_info_button = QPushButton("Refresh Device Info")
        self.start_capture_button = QPushButton("Start Capture")
        self.stop_capture_button = QPushButton("Stop Capture")
        self.export_package_button = QPushButton("Export Package")
        self.open_guide_button = QPushButton("Open Guide")
        self.device_selector_label.hide()
        self.device_selector.hide()
        self.device_selector.setMinimumWidth(220)
        self.refresh_device_info_button.setEnabled(False)
        self.start_capture_button.setEnabled(False)
        self.stop_capture_button.setEnabled(False)
        self.export_package_button.setEnabled(False)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        layout.addWidget(self.check_connection_button)
        layout.addWidget(self.device_selector_label)
        layout.addWidget(self.device_selector)
        layout.addWidget(self.refresh_device_info_button)
        layout.addWidget(self.start_capture_button)
        layout.addWidget(self.stop_capture_button)
        layout.addWidget(self.export_package_button)
        layout.addWidget(self.open_guide_button)
        layout.addStretch()

        self.check_connection_button.clicked.connect(self.check_connection_requested.emit)
        self.device_selector.currentIndexChanged.connect(self._emit_selected_device)
        self.refresh_device_info_button.clicked.connect(self.refresh_device_info_requested.emit)
        self.start_capture_button.clicked.connect(self.start_capture_requested.emit)
        self.stop_capture_button.clicked.connect(self.stop_capture_requested.emit)
        self.export_package_button.clicked.connect(self.export_package_requested.emit)
        self.open_guide_button.clicked.connect(self.open_guide_requested.emit)

    def set_device_choices(
        self,
        *,
        choices: list[tuple[str, str]],
        selected_serial: str | None,
        enabled: bool,
    ) -> None:
        visible = len(choices) > 1
        self.device_selector_label.setVisible(visible)
        self.device_selector.setVisible(visible)
        self.device_selector.blockSignals(True)
        self.device_selector.clear()
        for label, serial in choices:
            self.device_selector.addItem(label, serial)

        if visible and selected_serial:
            index = self.device_selector.findData(selected_serial)
            if index >= 0:
                self.device_selector.setCurrentIndex(index)

        self.device_selector.setEnabled(visible and enabled)
        self.device_selector.blockSignals(False)

    def set_capture_controls(
        self,
        *,
        ready_device: bool,
        capture_running: bool,
        export_ready: bool,
        device_selection_enabled: bool,
    ) -> None:
        self.device_selector.setEnabled(self.device_selector.isVisible() and device_selection_enabled)
        self.refresh_device_info_button.setEnabled(ready_device and not capture_running)
        self.start_capture_button.setEnabled(ready_device and not capture_running)
        self.stop_capture_button.setEnabled(capture_running)
        self.export_package_button.setEnabled(export_ready and not capture_running)

    def _emit_selected_device(self, index: int) -> None:
        serial = self.device_selector.itemData(index)
        if isinstance(serial, str) and serial:
            self.device_selected.emit(serial)
