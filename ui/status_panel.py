from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget


class StatusTile(QWidget):
    def __init__(self, title: str, initial_value: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("StatusTile")
        self.setProperty("tone", "info")

        title_label = QLabel(title)
        title_label.setObjectName("StatusTileTitle")

        self.dot_label = QLabel("●")
        self.dot_label.setObjectName("StatusDot")
        self.dot_label.setProperty("tone", "info")

        self.value_label = QLabel(initial_value)
        self.value_label.setObjectName("StatusTileValue")
        self.value_label.setProperty("tone", "info")
        self.value_label.setWordWrap(True)

        value_row = QWidget()
        value_row_layout = QHBoxLayout(value_row)
        value_row_layout.setContentsMargins(0, 0, 0, 0)
        value_row_layout.setSpacing(6)
        value_row_layout.addWidget(self.dot_label)
        value_row_layout.addWidget(self.value_label)
        value_row_layout.addStretch()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(6)
        layout.addWidget(title_label)
        layout.addWidget(value_row)

    def set_value(self, value: str, tone: str, tooltip: str | None = None) -> None:
        self.value_label.setText(value)
        tooltip_text = tooltip or value
        self.setToolTip(tooltip_text)
        self.value_label.setToolTip(tooltip_text)
        self.setProperty("tone", tone)
        self.dot_label.setProperty("tone", tone)
        self.value_label.setProperty("tone", tone)
        self.style().unpolish(self)
        self.style().polish(self)
        self.dot_label.style().unpolish(self.dot_label)
        self.dot_label.style().polish(self.dot_label)
        self.value_label.style().unpolish(self.value_label)
        self.value_label.style().polish(self.value_label)


class StatusPanel(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("SidebarCard")

        overview_widget = QWidget()
        overview_layout = QHBoxLayout(overview_widget)
        overview_layout.setContentsMargins(0, 0, 0, 0)
        overview_layout.setSpacing(8)

        self.system_tile = StatusTile("System Detected", "Detecting host system...")
        self.adb_tile = StatusTile("ADB Status", "Checking ADB...")
        self.connection_tile = StatusTile("Connection Status", "Waiting for connection check...")
        self.capture_tile = StatusTile("Capture Status", "Idle")

        overview_layout.addWidget(self.system_tile)
        overview_layout.addWidget(self.adb_tile)
        overview_layout.addWidget(self.connection_tile)
        overview_layout.addWidget(self.capture_tile)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(overview_widget)

    def set_system_status(self, message: str, tone: str = "info", tooltip: str | None = None) -> None:
        self.system_tile.set_value(message, tone, tooltip)

    def set_adb_status(self, message: str, tone: str = "info", tooltip: str | None = None) -> None:
        self.adb_tile.set_value(message, tone, tooltip)

    def set_connection_status(self, message: str, tone: str = "info", tooltip: str | None = None) -> None:
        self.connection_tile.set_value(message, tone, tooltip)

    def set_capture_status(self, message: str, tone: str = "warn", tooltip: str | None = None) -> None:
        self.capture_tile.set_value(message, tone, tooltip)
