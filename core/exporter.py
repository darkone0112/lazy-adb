from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import json
import platform
import shutil

from core.device_info import DeviceInfo
from core.device_state import DeviceConnection
from utils.file_helpers import ensure_directory, get_exports_root, safe_name, utc_timestamp


@dataclass(slots=True)
class ExportResult:
    success: bool
    message: str
    export_dir: Path | None = None
    archive_path: Path | None = None


class SupportPackageExporter:
    def __init__(self, exports_root: Path | None = None) -> None:
        self.exports_root = exports_root or get_exports_root()

    def create_package(
        self,
        *,
        connection: DeviceConnection,
        device_info: DeviceInfo | None,
        log_path: Path | None,
        adb_version_output: str | None,
    ) -> ExportResult:
        if device_info is None and log_path is None:
            return ExportResult(
                success=False,
                message="Nothing is available to export yet. Connect a device or capture logs first.",
            )

        serial = connection.serial or "unknown-device"
        package_name = f"support_package_{utc_timestamp()}_{safe_name(serial)}"
        export_dir = ensure_directory(self.exports_root / package_name)

        metadata = {
            "package_version": "0.1.0",
            "serial": connection.serial,
            "connection_state": connection.state.value,
            "connection_detail": connection.detail,
            "generated_on": platform.platform(),
            "adb_version_output": (adb_version_output or "").strip(),
        }
        metadata_path = export_dir / "metadata.json"
        metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

        if device_info is not None:
            device_info_path = export_dir / "device_info.json"
            device_info_path.write_text(json.dumps(asdict(device_info), indent=2), encoding="utf-8")

        if log_path is not None and log_path.exists():
            shutil.copy2(log_path, export_dir / "logcat.txt")

        archive_base = self.exports_root / package_name
        archive_path = Path(shutil.make_archive(str(archive_base), "zip", root_dir=export_dir.parent, base_dir=export_dir.name))

        return ExportResult(
            success=True,
            message=f"Support package created at {archive_path}.",
            export_dir=export_dir,
            archive_path=archive_path,
        )
