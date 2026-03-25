from __future__ import annotations

import os
from pathlib import Path
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtWidgets import QApplication

from core.device_info import DeviceInfo
from core.device_state import ConnectionMode, DeviceConnection, DeviceConnectionState
from ui.central_panel import CentralPanel


class WirelessMappingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_wireless_disconnect_keeps_raw_endpoint_after_device_info_load(self) -> None:
        panel = CentralPanel()
        panel.set_mode(ConnectionMode.WIFI)
        panel.show_guidance(
            DeviceConnection(
                state=DeviceConnectionState.READY,
                serial="192.168.1.22:40283",
                raw_state="device",
            )
        )

        panel.show_device_info(
            DeviceInfo(
                model="Pixel 8",
                manufacturer="Google",
                android_version="14",
                serial_number="R5CWC28JNYM",
                build_id="AP1A.240305.019",
                fingerprint="google/shiba/shiba:14/AP1A.240305.019:user/release-keys",
                device_name="shiba",
            )
        )

        self.assertEqual(panel.current_wireless_endpoint(), "192.168.1.22:40283")


if __name__ == "__main__":
    unittest.main()
