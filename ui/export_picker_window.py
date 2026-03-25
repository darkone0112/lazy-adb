from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton, QVBoxLayout, QWidget


class ExportPickerWindow(QDialog):
    log_selected = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Lazy ADB Wizard - Select Capture")
        self.resize(820, 520)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        title = QLabel("Select A Captured Log")
        title.setObjectName("PanelTitle")

        subtitle = QLabel("Choose which saved logcat session you want to package for export.")
        subtitle.setObjectName("PanelSubtitle")
        subtitle.setWordWrap(True)

        self.log_list = QListWidget()

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

        self.export_button.clicked.connect(self._emit_selected_log)
        self.cancel_button.clicked.connect(self.reject)
        self.log_list.itemDoubleClicked.connect(lambda _item: self._emit_selected_log())

    def set_logs(self, log_paths: list[Path]) -> None:
        self.log_list.clear()
        for path in log_paths:
            session_name = path.parent.name
            item = QListWidgetItem(f"{session_name}\n{path}")
            item.setData(256, str(path))
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
