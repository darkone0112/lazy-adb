from __future__ import annotations

from pathlib import Path
import json
import tempfile
import textwrap
import time
import unittest

from core.adb_manager import ADBManager
from core.device_info import DeviceInfo
from core.device_state import DeviceConnection, DeviceConnectionState
from core.exporter import SupportPackageExporter
from core.log_capture import LogCaptureManager


class LogCaptureManagerTests(unittest.TestCase):
    def test_start_and_stop_capture_writes_log_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir_name:
            temp_dir = Path(temp_dir_name)
            fake_adb = temp_dir / "fake-adb"
            fake_adb.write_text(
                textwrap.dedent(
                    """\
                    #!/bin/sh
                    if [ "$1" = "-s" ]; then
                      SERIAL="$2"
                      shift 2
                    fi

                    if [ "$1" = "logcat" ] && [ "$2" = "-c" ]; then
                      exit 0
                    fi

                    if [ "$1" = "logcat" ]; then
                      trap 'exit 0' TERM INT
                      i=0
                      while true; do
                        echo "[$SERIAL] line $i"
                        i=$((i + 1))
                        sleep 0.1
                      done
                    fi

                    echo "unsupported command" >&2
                    exit 1
                    """
                ),
                encoding="utf-8",
            )
            fake_adb.chmod(0o755)

            adb_manager = ADBManager(adb_path=fake_adb)
            capture_manager = LogCaptureManager(adb_manager, captures_root=temp_dir / "captures")

            start_result = capture_manager.start_capture("TEST123")
            self.assertTrue(start_result.success)
            self.assertIsNotNone(start_result.session)

            time.sleep(0.3)
            stop_result = capture_manager.stop_capture()

            self.assertTrue(stop_result.success)
            self.assertIsNotNone(stop_result.log_path)
            self.assertTrue(stop_result.log_path.exists())
            content = stop_result.log_path.read_text(encoding="utf-8")
            self.assertIn("[TEST123] line", content)


class SupportPackageExporterTests(unittest.TestCase):
    def test_create_package_writes_metadata_device_info_and_archive(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir_name:
            temp_dir = Path(temp_dir_name)
            log_path = temp_dir / "logcat.txt"
            log_path.write_text("example log line\n", encoding="utf-8")

            exporter = SupportPackageExporter(exports_root=temp_dir / "exports")
            result = exporter.create_package(
                connection=DeviceConnection(state=DeviceConnectionState.READY, serial="ABC123"),
                device_info=DeviceInfo(
                    model="Pixel 8",
                    manufacturer="Google",
                    android_version="14",
                    serial_number="ABC123",
                    build_id="AP1A",
                    fingerprint="google/example",
                    device_name="shiba",
                ),
                log_path=log_path,
                adb_version_output="Android Debug Bridge version 1.0.41",
            )

            self.assertTrue(result.success)
            self.assertIsNotNone(result.export_dir)
            self.assertIsNotNone(result.archive_path)
            self.assertTrue(result.export_dir.exists())
            self.assertTrue(result.archive_path.exists())
            self.assertTrue((result.export_dir / "metadata.json").exists())
            self.assertTrue((result.export_dir / "device_info.json").exists())
            self.assertTrue((result.export_dir / "logcat.txt").exists())

            metadata = json.loads((result.export_dir / "metadata.json").read_text(encoding="utf-8"))
            self.assertEqual(metadata["serial"], "ABC123")
            self.assertEqual(metadata["connection_state"], "ready")

    def test_create_package_requires_some_data(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir_name:
            temp_dir = Path(temp_dir_name)
            exporter = SupportPackageExporter(exports_root=temp_dir / "exports")
            result = exporter.create_package(
                connection=DeviceConnection(state=DeviceConnectionState.NO_DEVICE),
                device_info=None,
                log_path=None,
                adb_version_output=None,
            )

            self.assertFalse(result.success)


if __name__ == "__main__":
    unittest.main()
