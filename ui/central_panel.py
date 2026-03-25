from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedLayout,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from core.device_info import DeviceInfo
from core.device_state import ConnectionMode, DeviceConnection, DeviceConnectionState, describe_connection_state


DEVICE_FIELD_NAMES = [
    "Model",
    "Manufacturer",
    "Android Version",
    "Device Name",
    "Serial Number",
    "Build ID",
    "Fingerprint",
]


class CentralPanel(QWidget):
    open_wireless_setup_requested = Signal()
    disconnect_requested = Signal(str)
    device_selected = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._mode = ConnectionMode.USB
        self._wireless_connection: DeviceConnection | None = None
        self._wireless_action_target = ""

        self.stack = QStackedLayout(self)
        self.guidance_page = self._build_guidance_page()
        self.device_page = self._build_device_page()
        self.capture_page = self._build_capture_page()
        self.wireless_page = self._build_wireless_page()
        self.stack.addWidget(self.guidance_page)
        self.stack.addWidget(self.device_page)
        self.stack.addWidget(self.capture_page)
        self.stack.addWidget(self.wireless_page)

    def set_mode(self, mode: ConnectionMode) -> None:
        self._mode = mode
        if self.stack.currentWidget() is self.capture_page:
            return
        if mode is ConnectionMode.WIFI:
            self.stack.setCurrentWidget(self.wireless_page)
        else:
            self.stack.setCurrentWidget(self.guidance_page)

    def set_wireless_action_state(
        self,
        *,
        has_device: bool,
        pairing_enabled: bool,
        disconnect_enabled: bool,
    ) -> None:
        self.wireless_pair_new_button.setEnabled(pairing_enabled)
        self.wireless_disconnect_button.setVisible(has_device)
        self.wireless_disconnect_button.setEnabled(disconnect_enabled)

    def set_wireless_device_choices(
        self,
        *,
        choices: list[tuple[str, str]],
        selected_serial: str | None,
        enabled: bool,
    ) -> None:
        visible = bool(choices) or selected_serial is not None
        self.wireless_device_selector.setVisible(visible)
        self.wireless_device_selector.blockSignals(True)
        self.wireless_device_selector.clear()
        for label, serial in choices:
            self.wireless_device_selector.addItem(label, serial)
        if visible and selected_serial:
            index = self.wireless_device_selector.findData(selected_serial)
            if index >= 0:
                self.wireless_device_selector.setCurrentIndex(index)
            elif self.wireless_device_selector.count() == 0:
                self.wireless_device_selector.addItem(selected_serial, selected_serial)
        elif visible and self.wireless_device_selector.count() == 0:
            self.wireless_device_selector.addItem("No Device Selected", "")
        self.wireless_device_selector.setEnabled(visible and enabled and self.wireless_device_selector.count() > 1)
        self.wireless_device_selector.blockSignals(False)

    def show_guidance(self, connection: DeviceConnection) -> None:
        title, message, next_step = describe_connection_state(connection, mode=self._mode)
        if self._mode is ConnectionMode.WIFI:
            self._wireless_connection = connection
            self._wireless_action_target = connection.serial or ""
            self.wireless_title.setText(title)
            if connection.state is DeviceConnectionState.NO_DEVICE:
                self.wireless_status_label.setText(
                    "No wireless device paired or connected yet. Use the button Open Guide to see next steps."
                )
            else:
                self.wireless_status_label.setText(f"{message} Next step: {next_step}")
            self._set_field_map_defaults(self.wireless_device_fields)
            self.stack.setCurrentWidget(self.wireless_page)
            return

        self.guidance_title.setText(title)
        self.guidance_message.setText(message)
        self.guidance_next_step.setText(f"Next step: {next_step}")
        self.stack.setCurrentWidget(self.guidance_page)

    def show_device_info(self, info: DeviceInfo) -> None:
        field_map = self.wireless_device_fields if self._mode is ConnectionMode.WIFI else self.device_fields
        self._populate_field_map(field_map, info)
        if self._mode is ConnectionMode.WIFI:
            self.wireless_title.setText("Wireless ADB Setup")
            self.wireless_status_label.setText(f"Wireless target connected and ready: {info.serial_number}")
            self.stack.setCurrentWidget(self.wireless_page)
            return
        self.stack.setCurrentWidget(self.device_page)

    def show_ready_without_info(self, serial: str, message: str) -> None:
        field_map = self.wireless_device_fields if self._mode is ConnectionMode.WIFI else self.device_fields
        self._set_field_map_defaults(field_map)
        self._set_field(field_map, "Serial Number", serial)
        self._set_field(field_map, "Device Name", message)
        if self._mode is ConnectionMode.WIFI:
            self._wireless_connection = DeviceConnection(
                state=DeviceConnectionState.READY,
                serial=serial,
            )
            self._wireless_action_target = serial
            self.wireless_title.setText("Wireless ADB Setup")
            self.wireless_status_label.setText(message)
            self.stack.setCurrentWidget(self.wireless_page)
            return
        self.stack.setCurrentWidget(self.device_page)

    def show_capture_state(self, serial: str, log_path: str, message: str) -> None:
        self.capture_serial_label.setText(serial)
        self.capture_path_label.setText(log_path)
        self.capture_message_label.setText(message)
        self.stack.setCurrentWidget(self.capture_page)

    def current_wireless_endpoint(self) -> str:
        return self._wireless_action_target

    def _build_guidance_page(self) -> QWidget:
        card = QFrame()
        card.setObjectName("PrimaryCard")
        card.setFrameShape(QFrame.StyledPanel)

        self.guidance_title = QLabel("Connect Your Device")
        self.guidance_title.setObjectName("PanelTitle")

        self.guidance_message = QLabel(
            "No device is ready yet. Use the setup guide if you need detailed instructions."
        )
        self.guidance_message.setObjectName("PanelSubtitle")
        self.guidance_message.setWordWrap(True)

        self.guidance_next_step = QLabel(
            "Next step: Connect the device by USB and confirm USB debugging is enabled."
        )
        self.guidance_next_step.setObjectName("HintLabel")
        self.guidance_next_step.setWordWrap(True)

        help_box = QLabel("Need help with setup? Use the Open Guide button in the top action bar.")
        help_box.setObjectName("StepLabel")
        help_box.setWordWrap(True)

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(22, 22, 22, 22)
        card_layout.setSpacing(14)
        card_layout.addWidget(self.guidance_title)
        card_layout.addWidget(self.guidance_message)
        card_layout.addWidget(self.guidance_next_step)
        card_layout.addWidget(help_box)

        wrapper = QWidget()
        wrapper_layout = QVBoxLayout(wrapper)
        wrapper_layout.setContentsMargins(0, 0, 0, 0)
        wrapper_layout.addWidget(card)
        wrapper_layout.addStretch()
        return wrapper

    def _build_device_page(self) -> QWidget:
        card = QFrame()
        card.setObjectName("PrimaryCard")
        card.setFrameShape(QFrame.StyledPanel)

        heading = QLabel("Connected Device")
        heading.setObjectName("PanelTitle")

        subheading = QLabel("Device information retrieved from ADB `getprop`.")
        subheading.setObjectName("PanelSubtitle")
        subheading.setWordWrap(True)

        fields_widget, self.device_fields = self._build_device_fields()

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(22, 22, 22, 22)
        card_layout.setSpacing(14)
        card_layout.addWidget(heading)
        card_layout.addWidget(subheading)
        card_layout.addWidget(fields_widget)

        wrapper = QWidget()
        wrapper_layout = QVBoxLayout(wrapper)
        wrapper_layout.setContentsMargins(0, 0, 0, 0)
        wrapper_layout.addWidget(card)
        wrapper_layout.addStretch()
        return wrapper

    def _build_wireless_page(self) -> QWidget:
        card = QFrame()
        card.setObjectName("PrimaryCard")
        card.setFrameShape(QFrame.StyledPanel)

        self.wireless_title = QLabel("Wireless ADB Setup")
        self.wireless_title.setObjectName("PanelTitle")

        self.wireless_device_selector = QComboBox()
        self.wireless_device_selector.setMinimumWidth(260)
        self.wireless_device_selector.setToolTip("Choose the active wireless device when multiple targets are connected.")
        self.wireless_device_selector.hide()

        self.wireless_pair_new_button = QPushButton("Pair New Connection")
        self.wireless_disconnect_button = QPushButton("Disconnect")
        self.wireless_disconnect_button.hide()

        title_row = QWidget()
        title_layout = QHBoxLayout(title_row)
        title_layout.setContentsMargins(0, 0, 0, 0)
        title_layout.setSpacing(10)
        title_layout.addWidget(self.wireless_title)
        title_layout.addStretch()
        title_layout.addWidget(self.wireless_device_selector)
        title_layout.addWidget(self.wireless_pair_new_button)
        title_layout.addWidget(self.wireless_disconnect_button)

        self.wireless_status_label = QLabel("No wireless target connected yet.")
        self.wireless_status_label.setObjectName("HintLabel")
        self.wireless_status_label.setWordWrap(True)

        device_section = QLabel("Detected Device")
        device_section.setObjectName("SectionLabel")

        wireless_fields_widget, self.wireless_device_fields = self._build_device_fields()

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(22, 22, 22, 22)
        card_layout.setSpacing(14)
        card_layout.addWidget(title_row)
        card_layout.addWidget(self.wireless_status_label)
        card_layout.addWidget(device_section)
        card_layout.addWidget(wireless_fields_widget)

        self.wireless_pair_new_button.clicked.connect(self.open_wireless_setup_requested.emit)
        self.wireless_disconnect_button.clicked.connect(self._emit_disconnect_request)
        self.wireless_device_selector.currentIndexChanged.connect(self._emit_device_selected)
        self._set_field_map_defaults(self.wireless_device_fields)

        wrapper = QWidget()
        wrapper_layout = QVBoxLayout(wrapper)
        wrapper_layout.setContentsMargins(0, 0, 0, 0)
        wrapper_layout.addWidget(card)
        wrapper_layout.addStretch()
        return wrapper

    def _build_capture_page(self) -> QWidget:
        card = QFrame()
        card.setObjectName("PrimaryCard")
        card.setFrameShape(QFrame.StyledPanel)

        heading = QLabel("Capture In Progress")
        heading.setObjectName("PanelTitle")

        self.capture_message_label = QLabel(
            "The application is streaming logcat output to a file until you stop the capture."
        )
        self.capture_message_label.setObjectName("PanelSubtitle")
        self.capture_message_label.setWordWrap(True)

        details_widget = QWidget()
        details_layout = QFormLayout(details_widget)
        details_layout.setContentsMargins(0, 0, 0, 0)
        details_layout.setSpacing(10)

        self.capture_serial_label = QLabel("Unknown")
        self.capture_serial_label.setWordWrap(True)
        self.capture_path_label = QLabel("Unknown")
        self.capture_path_label.setWordWrap(True)

        details_layout.addRow("Serial Number:", self.capture_serial_label)
        details_layout.addRow("Log File:", self.capture_path_label)

        guidance = QLabel(
            "Leave the device connected, reproduce the issue, then click Stop Capture to save the session for export."
        )
        guidance.setObjectName("HintLabel")
        guidance.setWordWrap(True)

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(22, 22, 22, 22)
        card_layout.setSpacing(14)
        card_layout.addWidget(heading)
        card_layout.addWidget(self.capture_message_label)
        card_layout.addWidget(details_widget)
        card_layout.addWidget(guidance)

        wrapper = QWidget()
        wrapper_layout = QVBoxLayout(wrapper)
        wrapper_layout.setContentsMargins(0, 0, 0, 0)
        wrapper_layout.addWidget(card)
        wrapper_layout.addStretch()
        return wrapper

    def _build_device_fields(self) -> tuple[QWidget, dict[str, QLabel]]:
        fields_widget = QWidget()
        fields_layout = QFormLayout(fields_widget)
        fields_layout.setContentsMargins(0, 0, 0, 0)
        fields_layout.setHorizontalSpacing(14)
        fields_layout.setVerticalSpacing(12)

        field_map: dict[str, QLabel] = {}
        for field_name in DEVICE_FIELD_NAMES:
            value_label = QLabel("Unknown")
            value_label.setWordWrap(True)
            value_label.setObjectName("ValueLabel")
            field_map[field_name] = value_label

            row_widget = QWidget()
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(6)
            row_layout.addWidget(value_label, stretch=1)
            copy_button = self._build_copy_button(field_name)
            copy_button.clicked.connect(lambda _checked=False, label=value_label: self._copy_label(label))
            row_layout.addWidget(copy_button)
            fields_layout.addRow(f"{field_name}:", row_widget)

        return fields_widget, field_map

    def _populate_field_map(self, field_map: dict[str, QLabel], info: DeviceInfo) -> None:
        self._set_field(field_map, "Model", info.model)
        self._set_field(field_map, "Manufacturer", info.manufacturer)
        self._set_field(field_map, "Android Version", info.android_version)
        self._set_field(field_map, "Serial Number", info.serial_number)
        self._set_field(field_map, "Build ID", info.build_id)
        self._set_field(field_map, "Fingerprint", info.fingerprint)
        self._set_field(field_map, "Device Name", info.device_name)

    def _set_field_map_defaults(self, field_map: dict[str, QLabel]) -> None:
        for field_name in DEVICE_FIELD_NAMES:
            self._set_field(field_map, field_name, "Pending refresh")

    def _set_field(self, field_map: dict[str, QLabel], field_name: str, value: str) -> None:
        field_map[field_name].setText(value)

    def _copy_label(self, label: QLabel) -> None:
        QApplication.clipboard().setText(label.text())

    def _build_copy_button(self, field_name: str) -> QToolButton:
        button = QToolButton()
        button.setObjectName("CopyButton")
        button.setToolTip(f"Copy {field_name}")
        button.setText("⧉")
        font = QFont(button.font())
        font.setPointSize(9)
        button.setFont(font)
        button.setAutoRaise(True)
        button.setFixedSize(16, 16)
        return button

    def _emit_disconnect_request(self) -> None:
        self.disconnect_requested.emit(self.current_wireless_endpoint())

    def _emit_device_selected(self, index: int) -> None:
        serial = self.wireless_device_selector.itemData(index)
        if isinstance(serial, str) and serial:
            self.device_selected.emit(serial)
