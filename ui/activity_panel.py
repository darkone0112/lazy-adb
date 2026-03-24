from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPlainTextEdit, QVBoxLayout, QWidget


class ActivityPanel(QWidget):
    summary_changed = Signal(str, str)
    feed_text_changed = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("FeedCard")
        self._summary_tone = "info"

        badge = QLabel("Live")
        badge.setObjectName("HeaderBadge")
        badge.setProperty("tone", "violet")

        title = QLabel("Activity Feed")
        title.setObjectName("SectionTitle")

        title_row = QWidget()
        title_row_layout = QHBoxLayout(title_row)
        title_row_layout.setContentsMargins(0, 0, 0, 0)
        title_row_layout.setSpacing(8)
        title_row_layout.addWidget(title)
        title_row_layout.addWidget(badge)
        title_row_layout.addStretch()

        self.summary_label = QLabel("Application starting up.")
        self.summary_label.setObjectName("ActivitySummary")
        self.summary_label.setProperty("tone", "info")
        self.summary_label.setWordWrap(True)

        self.log_output = QPlainTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setPlaceholderText("The live activity stream will appear here.")
        log_font = QFont("Monospace")
        log_font.setStyleHint(QFont.StyleHint.Monospace)
        self.log_output.setFont(log_font)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)
        layout.addWidget(title_row)
        layout.addWidget(self.summary_label)
        layout.addWidget(self.log_output, stretch=1)

    def set_summary(self, message: str) -> None:
        self.set_summary_state(message, self._summary_tone)

    def set_summary_tone(self, tone: str) -> None:
        self.set_summary_state(self.summary_label.text(), tone)

    def set_summary_state(self, message: str, tone: str) -> None:
        self._summary_tone = tone
        self.summary_label.setText(message)
        self.summary_label.setProperty("tone", tone)
        self.summary_label.style().unpolish(self.summary_label)
        self.summary_label.style().polish(self.summary_label)
        self.summary_changed.emit(message, tone)

    def append_message(self, message: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_output.appendPlainText(f"[{timestamp}] {message}")
        self.feed_text_changed.emit(self.log_output.toPlainText())

    def append_stream_line(self, message: str) -> None:
        self.log_output.appendPlainText(message.rstrip("\n"))
        self.feed_text_changed.emit(self.log_output.toPlainText())

    def clear_feed(self) -> None:
        self.log_output.clear()
        self.feed_text_changed.emit("")

    def set_feed_text(self, text: str) -> None:
        self.log_output.setPlainText(text)
