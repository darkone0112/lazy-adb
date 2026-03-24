from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class WirelessSetupWindow(QMainWindow):
    pair_requested = Signal(str, str, str)
    connect_requested = Signal(str, str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Lazy ADB Wizard - Wireless Setup")
        self.resize(760, 300)

        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        title = QLabel("Pair or Connect a Wireless Device")
        title.setObjectName("PanelTitle")

        description = QLabel(
            "Use Pair Device for a new wireless session, then Connect with the debug port shown on the phone."
        )
        description.setObjectName("PanelSubtitle")
        description.setWordWrap(True)

        grid = QWidget()
        grid_layout = QGridLayout(grid)
        grid_layout.setContentsMargins(0, 0, 0, 0)
        grid_layout.setHorizontalSpacing(14)
        grid_layout.setVerticalSpacing(10)

        self.host_input = QLineEdit()
        self.host_input.setPlaceholderText("192.168.1.25")
        self.pair_port_input = QLineEdit()
        self.pair_port_input.setPlaceholderText("Pairing Port")
        self.pairing_code_input = QLineEdit()
        self.pairing_code_input.setPlaceholderText("Pairing Code")
        self.connect_port_input = QLineEdit()
        self.connect_port_input.setPlaceholderText("Connect Port")

        grid_layout.addWidget(self._label("Host / IP"), 0, 0)
        grid_layout.addWidget(self.host_input, 0, 1)
        grid_layout.addWidget(self._label("Pair Port"), 0, 2)
        grid_layout.addWidget(self.pair_port_input, 0, 3)
        grid_layout.addWidget(self._label("Pairing Code"), 1, 0)
        grid_layout.addWidget(self.pairing_code_input, 1, 1)
        grid_layout.addWidget(self._label("Connect Port"), 1, 2)
        grid_layout.addWidget(self.connect_port_input, 1, 3)
        grid_layout.setColumnStretch(1, 1)
        grid_layout.setColumnStretch(3, 1)

        button_row = QWidget()
        button_layout = QHBoxLayout(button_row)
        button_layout.setContentsMargins(0, 0, 0, 0)
        button_layout.setSpacing(10)
        self.pair_button = QPushButton("Pair Device")
        self.connect_button = QPushButton("Connect")
        button_layout.addWidget(self.pair_button)
        button_layout.addWidget(self.connect_button)
        button_layout.addStretch()

        self.pair_button.clicked.connect(self._emit_pair)
        self.connect_button.clicked.connect(self._emit_connect)

        layout.addWidget(title)
        layout.addWidget(description)
        layout.addWidget(grid)
        layout.addWidget(button_row)
        self.setCentralWidget(root)

    def set_controls_enabled(self, enabled: bool) -> None:
        self.host_input.setEnabled(enabled)
        self.pair_port_input.setEnabled(enabled)
        self.pairing_code_input.setEnabled(enabled)
        self.connect_port_input.setEnabled(enabled)
        self.pair_button.setEnabled(enabled)
        self.connect_button.setEnabled(enabled)

    def _emit_pair(self) -> None:
        self.pair_requested.emit(
            self.host_input.text().strip(),
            self.pair_port_input.text().strip(),
            self.pairing_code_input.text().strip(),
        )

    def _emit_connect(self) -> None:
        self.connect_requested.emit(
            self.host_input.text().strip(),
            self.connect_port_input.text().strip(),
        )

    def _label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("SectionLabel")
        return label
