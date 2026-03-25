from __future__ import annotations

from PySide6.QtWidgets import QFrame, QLabel, QMainWindow, QScrollArea, QVBoxLayout, QWidget

from core.device_state import ConnectionMode


class GuideWindow(QMainWindow):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Lazy ADB Wizard - Setup Guide")
        self.resize(1180, 860)
        self.setObjectName("GuideWindow")

        scroll = QScrollArea()
        scroll.setObjectName("GuideScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        container = QWidget()
        container.setObjectName("GuideContainer")
        self.content_layout = QVBoxLayout(container)
        self.content_layout.setContentsMargins(20, 20, 20, 20)
        self.content_layout.setSpacing(16)

        scroll.setWidget(container)
        self.setCentralWidget(scroll)

    def show_for_mode(self, mode: ConnectionMode) -> None:
        self._clear_content()
        if mode is ConnectionMode.WIFI:
            self.setWindowTitle("Lazy ADB Wizard - Wi-Fi Setup Guide")
            self._populate_wifi_guide()
        else:
            self.setWindowTitle("Lazy ADB Wizard - USB Setup Guide")
            self._populate_usb_guide()
        self.showMaximized()
        self.raise_()
        self.activateWindow()

    def _populate_usb_guide(self) -> None:
        self.content_layout.addWidget(self._title("USB ADB Setup Guide"))
        self.content_layout.addWidget(
            self._subtitle(
                "Use this guide when a device is not detected over USB or when the phone has never been prepared for ADB before."
            )
        )
        self.content_layout.addWidget(
            self._step_card(
                "1. Enable Developer Options",
                [
                    "Open Settings on the Android device.",
                    "Go to About phone.",
                    "Find Build number.",
                    "Tap Build number 7 times.",
                    "If the device asks for the PIN, pattern, or password, enter it to confirm.",
                    "After the seventh tap, Android should confirm that Developer Options are enabled.",
                ],
            )
        )
        self.content_layout.addWidget(
            self._step_card(
                "2. Turn On USB Debugging",
                [
                    "Go back to the main Settings screen.",
                    "Open Developer Options. On many devices this is under System or Additional settings.",
                    "Enable USB debugging.",
                    "If Android shows a confirmation dialog, accept it.",
                ],
            )
        )
        self.content_layout.addWidget(
            self._step_card(
                "3. Restart The Device",
                [
                    "Restart the phone after enabling USB debugging.",
                    "Wait until Android fully boots back to the home screen.",
                    "Keep the screen unlocked before connecting it to the computer again.",
                ],
            )
        )
        self.content_layout.addWidget(
            self._step_card(
                "4. Connect And Authorize",
                [
                    "Connect the device to the computer with a USB cable.",
                    "Use a data-capable cable, not a charge-only cable.",
                    "When the Allow USB debugging prompt appears on the device, tap Allow.",
                    "If available, enable Always allow from this computer.",
                ],
            )
        )
        self.content_layout.addWidget(
            self._step_card(
                "5. If Detection Still Fails",
                [
                    "Reconnect the cable and try a different USB port.",
                    "Unlock the phone again and watch for hidden authorization prompts.",
                    "Try a different cable if the device only charges and does not show up to ADB.",
                    "Run Check Connection again in the app.",
                ],
            )
        )
        self.content_layout.addStretch()

    def _populate_wifi_guide(self) -> None:
        self.content_layout.addWidget(self._title("Wi-Fi ADB Setup Guide"))
        self.content_layout.addWidget(
            self._subtitle(
                "Use this guide when you want to pair and connect the device over wireless debugging instead of USB."
            )
        )
        self.content_layout.addWidget(
            self._step_card(
                "1. Enable Developer Options",
                [
                    "Open Settings on the Android device.",
                    "Go to About phone.",
                    "Find Build number.",
                    "Tap Build number 7 times.",
                    "If the device asks for the PIN, pattern, or password, enter it.",
                    "Android should confirm that Developer Options are now enabled.",
                ],
            )
        )
        self.content_layout.addWidget(
            self._step_card(
                "2. Enable Debugging Options",
                [
                    "Go back to the main Settings screen.",
                    "Open Developer Options.",
                    "Enable USB debugging if it is still off.",
                    "Enable Wireless debugging.",
                    "Accept any confirmation dialog Android shows.",
                ],
            )
        )
        self.content_layout.addWidget(
            self._step_card(
                "3. Restart The Device",
                [
                    "Restart the phone after enabling debugging.",
                    "Wait until the device finishes booting and reconnects to Wi-Fi.",
                    "Return to Developer Options and confirm Wireless debugging is still enabled.",
                ],
            )
        )
        self.content_layout.addWidget(
            self._step_card(
                "4. Understand The Two Ports First",
                [
                    "Wireless debugging shows two different ports that are used for two different actions.",
                    "The connect port is shown on the main Wireless debugging screen, next to the device IP address.",
                    "The pairing port is only shown after tapping Pair device with pairing code.",
                    "The pairing code is also only shown inside Pair device with pairing code, next to the same device IP address.",
                    "The IP address stays the same, but the connect port and pairing port are different values.",
                ],
            )
        )
        self.content_layout.addWidget(
            self._step_card(
                "5. Fill The App In The Easiest Order",
                [
                    "In Wi-Fi mode, enter the device IP in Host / IP.",
                    "While you are already on the main Wireless debugging screen, enter the connect port first, because it is the first port Android shows next to the IP address.",
                    "After that, tap Pair device with pairing code on the phone.",
                    "Then enter the pairing port and the pairing code shown in that pairing screen.",
                ],
            )
        )
        self.content_layout.addWidget(
            self._step_card(
                "6. Pair The Device",
                [
                    "With Host / IP, Pair Port, and Pairing Code filled in, click Pair Device in Lazy ADB Wizard.",
                    "Wait for Android Debug Bridge to confirm that pairing succeeded.",
                ],
            )
        )
        self.content_layout.addWidget(
            self._step_card(
                "7. Connect The Wireless Session",
                [
                    "After pairing succeeds, use the same Host / IP and the connect port you filled in earlier.",
                    "Click Connect.",
                    "Once connected, the device should appear as ready in the app.",
                ],
            )
        )
        self.content_layout.addWidget(
            self._step_card(
                "8. If Pairing Or Connect Fails",
                [
                    "Make sure the phone and computer are on the same network.",
                    "Reopen Wireless debugging and get a fresh pairing code if the current one expired.",
                    "Confirm the IP address did not change after restart or reconnect.",
                    "Try pairing again, then connect again.",
                ],
            )
        )
        self.content_layout.addStretch()

    def _clear_content(self) -> None:
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _title(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("PanelTitle")
        label.setWordWrap(True)
        return label

    def _subtitle(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("PanelSubtitle")
        label.setWordWrap(True)
        return label

    def _step_card(self, title: str, steps: list[str]) -> QFrame:
        card = QFrame()
        card.setObjectName("PrimaryCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)

        heading = QLabel(title)
        heading.setObjectName("SectionTitle")
        heading.setWordWrap(True)
        layout.addWidget(heading)

        for index, step in enumerate(steps, start=1):
            label = QLabel(f"{index}. {step}")
            label.setObjectName("StepLabel")
            label.setWordWrap(True)
            layout.addWidget(label)

        return card
