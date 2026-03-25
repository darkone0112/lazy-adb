from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QLineEdit,
    QMainWindow,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)


class AdvancedWindow(QMainWindow):
    command_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._base_title = "Lazy ADB Wizard - Advanced"
        self.setWindowTitle(self._base_title)
        self.resize(980, 620)

        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)

        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setPlaceholderText("ADB terminal output appears here. Type a subcommand below and press Enter.")
        log_font = QFont("Monospace")
        log_font.setStyleHint(QFont.StyleHint.Monospace)
        self.output.setFont(log_font)

        self.command_input = QLineEdit()
        self.command_input.setPlaceholderText("shell getprop")

        layout.addWidget(self.output, stretch=1)
        layout.addWidget(self.command_input)
        self.setCentralWidget(root)

        self.command_input.returnPressed.connect(self._emit_command)

    def set_target(self, label: str, enabled: bool) -> None:
        title_suffix = label.removeprefix("Target: ").strip()
        self.setWindowTitle(f"{self._base_title} - {title_suffix}")
        self.command_input.setEnabled(enabled)
        self.command_input.setPlaceholderText(
            "shell getprop" if enabled else "No ready device selected for Advanced commands."
        )

    def append_output(self, text: str) -> None:
        self.output.appendPlainText(text)

    def _emit_command(self) -> None:
        command = self.command_input.text().strip()
        if not command:
            return
        self.command_requested.emit(command)
        self.command_input.clear()
