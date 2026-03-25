from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import json
import platform
import shutil
import tempfile

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
        destination_path: Path | None = None,
    ) -> ExportResult:
        if device_info is None and log_path is None:
            return ExportResult(
                success=False,
                message="Nothing is available to export yet. Connect a device or capture logs first.",
            )

        serial = connection.serial or "unknown-device"
        package_name = f"support_package_{utc_timestamp()}_{safe_name(serial)}"
        if destination_path is None:
            export_dir = ensure_directory(self.exports_root / package_name)
            archive_base = self.exports_root / package_name
            archive_path = self._write_export_contents(
                export_dir=export_dir,
                archive_base=archive_base,
                connection=connection,
                device_info=device_info,
                log_path=log_path,
                adb_version_output=adb_version_output,
            )
            return ExportResult(
                success=True,
                message=f"Support package created at {archive_path}.",
                export_dir=export_dir,
                archive_path=archive_path,
            )

        destination_path = destination_path.with_suffix(".zip")
        ensure_directory(destination_path.parent)
        with tempfile.TemporaryDirectory(prefix="lazy_adb_export_") as temp_dir_name:
            temp_root = Path(temp_dir_name)
            export_dir = ensure_directory(temp_root / package_name)
            archive_base = temp_root / package_name
            temp_archive = self._write_export_contents(
                export_dir=export_dir,
                archive_base=archive_base,
                connection=connection,
                device_info=device_info,
                log_path=log_path,
                adb_version_output=adb_version_output,
            )
            shutil.copy2(temp_archive, destination_path)
            archive_path = destination_path

        return ExportResult(
            success=True,
            message=f"Support package created at {archive_path}.",
            export_dir=None,
            archive_path=archive_path,
        )

    def _write_export_contents(
        self,
        *,
        export_dir: Path,
        archive_base: Path,
        connection: DeviceConnection,
        device_info: DeviceInfo | None,
        log_path: Path | None,
        adb_version_output: str | None,
    ) -> Path:
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

        return Path(
            shutil.make_archive(
                str(archive_base),
                "zip",
                root_dir=export_dir.parent,
                base_dir=export_dir.name,
            )
        )
