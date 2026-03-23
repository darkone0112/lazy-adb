from __future__ import annotations

from pathlib import Path
import platform
import sys


def get_app_root() -> Path:
    if getattr(sys, "frozen", False):
        if hasattr(sys, "_MEIPASS"):
            return Path(sys._MEIPASS)  # type: ignore[attr-defined]
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def get_platform_key() -> str:
    system_name = platform.system().lower()
    if system_name == "windows":
        return "windows"
    if system_name == "linux":
        return "linux"
    if system_name == "darwin":
        return "darwin"
    raise RuntimeError(f"Unsupported platform for the MVP: {platform.system()}")


def get_platform_tools_dir(platform_key: str | None = None, *, app_root: Path | None = None) -> Path:
    resolved_root = app_root or get_app_root()
    resolved_platform = platform_key or get_platform_key()
    return resolved_root / "resources" / "platform-tools" / resolved_platform


def get_bundled_adb_path(platform_key: str | None = None) -> Path:
    platform_key = platform_key or get_platform_key()
    executable_name = "adb.exe" if platform_key == "windows" else "adb"
    return get_platform_tools_dir(platform_key) / executable_name


def get_platform_tools_download_url(platform_key: str | None = None) -> str:
    resolved_platform = platform_key or get_platform_key()
    urls = {
        "windows": "https://dl.google.com/android/repository/platform-tools-latest-windows.zip",
        "linux": "https://dl.google.com/android/repository/platform-tools-latest-linux.zip",
        "darwin": "https://dl.google.com/android/repository/platform-tools-latest-darwin.zip",
    }
    return urls[resolved_platform]


def describe_host_system() -> str:
    system_name = platform.system()
    if system_name == "Darwin":
        return "macOS"
    return system_name
