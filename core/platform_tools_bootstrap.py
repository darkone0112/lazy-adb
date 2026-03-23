from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
import stat
import tempfile
import urllib.request
import zipfile

from utils.file_helpers import ensure_directory
from utils.platform_paths import (
    get_bundled_adb_path,
    get_platform_key,
    get_platform_tools_dir,
    get_platform_tools_download_url,
)


@dataclass(slots=True)
class PlatformToolsBootstrapResult:
    success: bool
    message: str
    downloaded: bool = False
    platform_key: str | None = None
    target_dir: Path | None = None


class PlatformToolsBootstrapper:
    def __init__(self, app_root: Path | None = None) -> None:
        self.app_root = app_root

    def is_installed(self, platform_key: str | None = None) -> bool:
        return self.get_adb_path(platform_key).exists()

    def get_adb_path(self, platform_key: str | None = None) -> Path:
        if self.app_root is None:
            return get_bundled_adb_path(platform_key)
        return get_platform_tools_dir(platform_key, app_root=self.app_root) / self._adb_name(platform_key)

    def ensure_present(
        self,
        *,
        platform_key: str | None = None,
        progress_cb: callable | None = None,
        download_url: str | None = None,
    ) -> PlatformToolsBootstrapResult:
        resolved_platform = platform_key or get_platform_key()
        if self.is_installed(resolved_platform):
            return PlatformToolsBootstrapResult(
                success=True,
                message="Bundled platform-tools are already present.",
                downloaded=False,
                platform_key=resolved_platform,
                target_dir=self._target_dir(resolved_platform),
            )
        return self.download_and_install(
            platform_key=resolved_platform,
            progress_cb=progress_cb,
            download_url=download_url,
        )

    def download_and_install(
        self,
        *,
        platform_key: str | None = None,
        progress_cb: callable | None = None,
        download_url: str | None = None,
    ) -> PlatformToolsBootstrapResult:
        resolved_platform = platform_key or get_platform_key()
        target_dir = self._target_dir(resolved_platform)
        url = download_url or get_platform_tools_download_url(resolved_platform)

        try:
            ensure_directory(target_dir)
            with tempfile.TemporaryDirectory() as temp_dir_name:
                temp_dir = Path(temp_dir_name)
                archive_path = temp_dir / "platform-tools.zip"
                extract_dir = temp_dir / "extract"

                self._progress(progress_cb, f"Downloading platform-tools for {resolved_platform}...")
                self._download_archive(url, archive_path, progress_cb)

                self._progress(progress_cb, "Extracting platform-tools archive...")
                with zipfile.ZipFile(archive_path) as archive:
                    archive.extractall(extract_dir)

                package_dir = extract_dir / "platform-tools"
                if not package_dir.exists():
                    raise FileNotFoundError("The downloaded archive did not contain a platform-tools folder.")

                self._progress(progress_cb, "Installing platform-tools into the application resources...")
                self._replace_target_contents(package_dir, target_dir)
                self._ensure_executable_permissions(target_dir, resolved_platform)
        except Exception as exc:
            return PlatformToolsBootstrapResult(
                success=False,
                message=f"Could not prepare bundled platform-tools: {exc}",
                downloaded=False,
                platform_key=resolved_platform,
                target_dir=target_dir,
            )

        return PlatformToolsBootstrapResult(
            success=True,
            message=f"Platform-tools for {resolved_platform} were downloaded successfully.",
            downloaded=True,
            platform_key=resolved_platform,
            target_dir=target_dir,
        )

    def _target_dir(self, platform_key: str) -> Path:
        return get_platform_tools_dir(platform_key, app_root=self.app_root)

    def _adb_name(self, platform_key: str | None) -> str:
        resolved_platform = platform_key or get_platform_key()
        return "adb.exe" if resolved_platform == "windows" else "adb"

    def _download_archive(self, url: str, archive_path: Path, progress_cb: callable | None) -> None:
        with urllib.request.urlopen(url) as response, archive_path.open("wb") as output_file:
            total_length = response.headers.get("Content-Length")
            total_bytes = int(total_length) if total_length and total_length.isdigit() else None
            downloaded = 0
            chunk_size = 1024 * 128
            last_progress_bucket = -1

            while True:
                chunk = response.read(chunk_size)
                if not chunk:
                    break
                output_file.write(chunk)
                downloaded += len(chunk)
                if total_bytes:
                    progress = int(downloaded / total_bytes * 100)
                    progress_bucket = progress // 10
                    if progress_bucket != last_progress_bucket:
                        last_progress_bucket = progress_bucket
                        self._progress(progress_cb, f"Downloaded {progress}% of platform-tools archive...")

    def _replace_target_contents(self, source_dir: Path, target_dir: Path) -> None:
        ensure_directory(target_dir)
        for child in target_dir.iterdir():
            if child.name == ".gitkeep":
                continue
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()

        for child in source_dir.iterdir():
            destination = target_dir / child.name
            if child.is_dir():
                shutil.copytree(child, destination)
            else:
                shutil.copy2(child, destination)

    def _ensure_executable_permissions(self, target_dir: Path, platform_key: str) -> None:
        if platform_key == "windows":
            return

        for path in target_dir.rglob("*"):
            if not path.is_file():
                continue
            current_mode = path.stat().st_mode
            path.chmod(current_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    def _progress(self, progress_cb: callable | None, message: str) -> None:
        if progress_cb is not None:
            progress_cb(message)
