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
    raise RuntimeError(f"Unsupported platform for the MVP: {platform.system()}")


def get_bundled_adb_path() -> Path:
    platform_key = get_platform_key()
    executable_name = "adb.exe" if platform_key == "windows" else "adb"
    return get_app_root() / "resources" / "platform-tools" / platform_key / executable_name


def describe_host_system() -> str:
    system_name = platform.system()
    if system_name == "Darwin":
        return "macOS"
    return system_name
