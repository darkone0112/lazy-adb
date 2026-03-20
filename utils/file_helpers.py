from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import re

from utils.platform_paths import get_app_root


def ensure_directory(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_output_root() -> Path:
    return ensure_directory(get_app_root() / "output")


def get_captures_root() -> Path:
    return ensure_directory(get_output_root() / "captures")


def get_exports_root() -> Path:
    return ensure_directory(get_output_root() / "exports")


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def safe_name(value: str, default: str = "unknown") -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._-")
    return cleaned or default
