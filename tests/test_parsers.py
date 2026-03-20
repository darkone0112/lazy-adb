from __future__ import annotations

import unittest

from core.device_info import detect_getprop_problem, parse_getprop_output
from core.device_state import (
    DeviceConnectionState,
    normalize_device_state,
    parse_adb_devices_output,
    select_preferred_device,
)


class DeviceStateParsingTests(unittest.TestCase):
    def test_parse_devices_ignores_header_and_empty_lines(self) -> None:
        output = "List of devices attached\n\nABC123\tdevice\n"
        devices = parse_adb_devices_output(output)

        self.assertEqual(len(devices), 1)
        self.assertEqual(devices[0].serial, "ABC123")
        self.assertEqual(devices[0].raw_state, "device")

    def test_select_preferred_device_prefers_ready(self) -> None:
        output = (
            "List of devices attached\n"
            "UNAUTH01\tunauthorized\n"
            "READY01\tdevice\n"
            "OFF01\toffline\n"
        )
        devices = parse_adb_devices_output(output)
        connection = select_preferred_device(devices)

        self.assertEqual(connection.state, DeviceConnectionState.READY)
        self.assertEqual(connection.serial, "READY01")

    def test_normalize_device_state_maps_supported_values(self) -> None:
        self.assertEqual(normalize_device_state("device"), DeviceConnectionState.READY)
        self.assertEqual(normalize_device_state("unauthorized"), DeviceConnectionState.UNAUTHORIZED)
        self.assertEqual(normalize_device_state("offline"), DeviceConnectionState.OFFLINE)
        self.assertEqual(normalize_device_state("mystery"), DeviceConnectionState.ERROR)


class DeviceInfoParsingTests(unittest.TestCase):
    def test_parse_getprop_output_extracts_expected_fields(self) -> None:
        output = "\n".join(
            [
                "[ro.product.model]: [Pixel 8]",
                "[ro.product.manufacturer]: [Google]",
                "[ro.build.version.release]: [14]",
                "[ro.product.device]: [shiba]",
                "[ro.build.id]: [AP1A.240305.019]",
                "[ro.build.fingerprint]: [google/shiba/shiba:14/AP1A.240305.019:user/release-keys]",
            ]
        )

        info = parse_getprop_output(output, serial_number="ABC123")

        self.assertEqual(info.model, "Pixel 8")
        self.assertEqual(info.manufacturer, "Google")
        self.assertEqual(info.android_version, "14")
        self.assertEqual(info.device_name, "shiba")
        self.assertEqual(info.build_id, "AP1A.240305.019")
        self.assertEqual(info.serial_number, "ABC123")

    def test_detect_getprop_problem_for_missing_command(self) -> None:
        problem = detect_getprop_problem("/bin/sh: getprop: not found\n")
        self.assertIsNotNone(problem)
        self.assertIn("not available", problem)

    def test_detect_getprop_problem_for_non_android_output(self) -> None:
        problem = detect_getprop_problem("plain shell output without Android properties\n")
        self.assertIsNotNone(problem)
        self.assertIn("did not return recognizable Android system properties", problem)


if __name__ == "__main__":
    unittest.main()
