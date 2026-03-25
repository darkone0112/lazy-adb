from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton, QVBoxLayout, QWidget


class ExportPickerWindow(QDialog):
    log_selected = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ExportPickerWindow")
        self.setWindowTitle("Lazy ADB Wizard - Select Capture")
        self.resize(820, 520)

        root = QWidget()
        root.setObjectName("ExportPickerRoot")
        layout = QVBoxLayout(root)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        title = QLabel("Select A Captured Log")
        title.setObjectName("PanelTitle")

        subtitle = QLabel("Choose which saved logcat session you want to package for export.")
        subtitle.setObjectName("PanelSubtitle")
        subtitle.setWordWrap(True)

        self.log_list = QListWidget()
        self.log_list.setObjectName("ExportLogList")
        self.log_list.setAlternatingRowColors(False)
        self.log_list.setUniformItemSizes(False)
        self.log_list.setWordWrap(True)
        self.log_list.setSpacing(4)

        button_row = QWidget()
        button_layout = QHBoxLayout(button_row)
        button_layout.setContentsMargins(0, 0, 0, 0)
        button_layout.setSpacing(10)
        self.export_button = QPushButton("Export Selected Log")
        self.cancel_button = QPushButton("Cancel")
        button_layout.addStretch()
        button_layout.addWidget(self.cancel_button)
        button_layout.addWidget(self.export_button)

        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(self.log_list, stretch=1)
        layout.addWidget(button_row)
        dialog_layout = QVBoxLayout(self)
        dialog_layout.setContentsMargins(0, 0, 0, 0)
        dialog_layout.addWidget(root)

        self.export_button.clicked.connect(self._emit_selected_log)
        self.cancel_button.clicked.connect(self.reject)
        self.log_list.itemDoubleClicked.connect(lambda _item: self._emit_selected_log())

    def set_logs(self, log_paths: list[Path]) -> None:
        self.log_list.clear()
        for path in log_paths:
            item = QListWidgetItem(self._describe_log_path(path))
            item.setData(256, str(path))
            item.setToolTip(str(path))
            item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            self.log_list.addItem(item)
        if self.log_list.count():
            self.log_list.setCurrentRow(0)

    def _emit_selected_log(self) -> None:
        item = self.log_list.currentItem()
        if item is None:
            return
        log_path = item.data(256)
        if isinstance(log_path, str) and log_path:
            self.log_selected.emit(log_path)
            self.accept()

    def _describe_log_path(self, path: Path) -> str:
        session_name = path.parent.name
        timestamp, _, serial = session_name.partition("_")
        readable_timestamp = self._format_timestamp(timestamp)
        serial_display = serial or "Unknown device"
        return f"{readable_timestamp}\nDevice: {serial_display}"

    def _format_timestamp(self, value: str) -> str:
        try:
            parsed = datetime.strptime(value, "%Y%m%dT%H%M%SZ")
        except ValueError:
            return value
        return parsed.strftime("%Y-%m-%d %H:%M:%S UTC")
