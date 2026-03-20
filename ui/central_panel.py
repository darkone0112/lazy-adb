from __future__ import annotations

from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QStackedLayout,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from core.device_info import DeviceInfo
from core.device_state import DeviceConnection, describe_connection_state


class CentralPanel(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self.stack = QStackedLayout(self)
        self.guidance_page = self._build_guidance_page()
        self.device_page = self._build_device_page()
        self.capture_page = self._build_capture_page()
        self.stack.addWidget(self.guidance_page)
        self.stack.addWidget(self.device_page)
        self.stack.addWidget(self.capture_page)

    def show_guidance(self, connection: DeviceConnection) -> None:
        title, message, next_step = describe_connection_state(connection)
        self.guidance_title.setText(title)
        self.guidance_message.setText(message)
        self.guidance_next_step.setText(f"Next step: {next_step}")
        self.stack.setCurrentWidget(self.guidance_page)

    def show_device_info(self, info: DeviceInfo) -> None:
        self._set_device_field("Model", info.model)
        self._set_device_field("Manufacturer", info.manufacturer)
        self._set_device_field("Android Version", info.android_version)
        self._set_device_field("Serial Number", info.serial_number)
        self._set_device_field("Build ID", info.build_id)
        self._set_device_field("Fingerprint", info.fingerprint)
        self._set_device_field("Device Name", info.device_name)
        self.stack.setCurrentWidget(self.device_page)

    def show_ready_without_info(self, serial: str, message: str) -> None:
        self._set_device_field("Model", "Pending refresh")
        self._set_device_field("Manufacturer", "Pending refresh")
        self._set_device_field("Android Version", "Pending refresh")
        self._set_device_field("Serial Number", serial)
        self._set_device_field("Build ID", "Pending refresh")
        self._set_device_field("Fingerprint", "Pending refresh")
        self._set_device_field("Device Name", message)
        self.stack.setCurrentWidget(self.device_page)

    def show_capture_state(self, serial: str, log_path: str, message: str) -> None:
        self.capture_serial_label.setText(serial)
        self.capture_path_label.setText(log_path)
        self.capture_message_label.setText(message)
        self.stack.setCurrentWidget(self.capture_page)

    def _build_guidance_page(self) -> QWidget:
        card = QFrame()
        card.setObjectName("PrimaryCard")
        card.setFrameShape(QFrame.StyledPanel)

        self.guidance_title = QLabel("Connect Your Device")
        self.guidance_title.setObjectName("PanelTitle")

        self.guidance_message = QLabel(
            "No device is ready yet. Follow the setup steps below before checking again."
        )
        self.guidance_message.setObjectName("PanelSubtitle")
        self.guidance_message.setWordWrap(True)

        self.guidance_next_step = QLabel(
            "Next step: Connect the device by USB and confirm USB debugging is enabled."
        )
        self.guidance_next_step.setObjectName("HintLabel")
        self.guidance_next_step.setWordWrap(True)

        steps_layout = QVBoxLayout()
        steps_layout.setSpacing(10)
        for number, step in enumerate(
            [
                "Connect the Android device with a USB cable.",
                "Open Settings on the device.",
                "Enable Developer Options.",
                "Enable USB Debugging.",
                "Accept the authorization prompt on the device if it appears.",
            ],
            start=1,
        ):
            label = QLabel(f"{number}. {step}")
            label.setObjectName("StepLabel")
            label.setWordWrap(True)
            steps_layout.addWidget(label)

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(22, 22, 22, 22)
        card_layout.setSpacing(14)
        card_layout.addWidget(self.guidance_title)
        card_layout.addWidget(self.guidance_message)
        card_layout.addWidget(self.guidance_next_step)
        section_label = QLabel("Setup Guide")
        section_label.setObjectName("SectionLabel")
        card_layout.addWidget(section_label)
        card_layout.addLayout(steps_layout)

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

        fields_widget = QWidget()
        fields_layout = QFormLayout(fields_widget)
        fields_layout.setContentsMargins(0, 0, 0, 0)
        fields_layout.setHorizontalSpacing(14)
        fields_layout.setVerticalSpacing(12)

        self.device_fields: dict[str, QLabel] = {}
        for field_name in [
            "Model",
            "Manufacturer",
            "Android Version",
            "Device Name",
            "Serial Number",
            "Build ID",
            "Fingerprint",
        ]:
            value_label = QLabel("Unknown")
            value_label.setWordWrap(True)
            value_label.setObjectName("ValueLabel")
            self.device_fields[field_name] = value_label

            row_widget = QWidget()
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(6)
            row_layout.addWidget(value_label, stretch=1)
            copy_button = self._build_copy_button(field_name)
            copy_button.clicked.connect(lambda _checked=False, name=field_name: self._copy_field(name))
            row_layout.addWidget(copy_button)
            fields_layout.addRow(f"{field_name}:", row_widget)

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

    def _set_device_field(self, field_name: str, value: str) -> None:
        self.device_fields[field_name].setText(value)

    def _copy_field(self, field_name: str) -> None:
        QApplication.clipboard().setText(self.device_fields[field_name].text())

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
