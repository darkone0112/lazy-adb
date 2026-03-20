from __future__ import annotations

from PySide6.QtWidgets import QGridLayout, QLabel, QVBoxLayout, QWidget


class StatusTile(QWidget):
    def __init__(self, title: str, initial_value: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("StatusTile")
        self.setProperty("tone", "info")

        title_label = QLabel(title)
        title_label.setObjectName("StatusTileTitle")

        self.value_label = QLabel(initial_value)
        self.value_label.setObjectName("StatusTileValue")
        self.value_label.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(6)
        layout.addWidget(title_label)
        layout.addWidget(self.value_label)

    def set_value(self, value: str, tone: str) -> None:
        self.value_label.setText(value)
        self.setProperty("tone", tone)
        self.style().unpolish(self)
        self.style().polish(self)


class StatusPanel(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("SidebarCard")

        title = QLabel("Status Overview")
        title.setObjectName("SectionTitle")

        overview_widget = QWidget()
        overview_layout = QGridLayout(overview_widget)
        overview_layout.setContentsMargins(0, 0, 0, 0)
        overview_layout.setHorizontalSpacing(10)
        overview_layout.setVerticalSpacing(10)

        self.system_tile = StatusTile("System Detected", "Detecting host system...")
        self.adb_tile = StatusTile("ADB Status", "Checking ADB...")
        self.connection_tile = StatusTile("Connection Status", "Waiting for connection check...")
        self.capture_tile = StatusTile("Capture Status", "Idle")

        overview_layout.addWidget(self.system_tile, 0, 0)
        overview_layout.addWidget(self.adb_tile, 0, 1)
        overview_layout.addWidget(self.connection_tile, 1, 0)
        overview_layout.addWidget(self.capture_tile, 1, 1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)
        layout.addWidget(title)
        layout.addWidget(overview_widget)
        layout.addStretch()

    def set_system_status(self, message: str, tone: str = "info") -> None:
        self.system_tile.set_value(message, tone)

    def set_adb_status(self, message: str, tone: str = "info") -> None:
        self.adb_tile.set_value(message, tone)

    def set_connection_status(self, message: str, tone: str = "info") -> None:
        self.connection_tile.set_value(message, tone)

    def set_capture_status(self, message: str, tone: str = "warn") -> None:
        self.capture_tile.set_value(message, tone)
