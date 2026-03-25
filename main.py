from __future__ import annotations

from pathlib import Path
import sys


def _find_app_icon() -> Path | None:
    from utils.platform_paths import get_app_root

    candidates = [
        get_app_root() / "android-logo.ico",
        Path(sys.executable).resolve().parent / "android-logo.ico",
        Path(__file__).resolve().parent / "android-logo.ico",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def main() -> int:
    try:
        from PySide6.QtGui import QIcon
        from PySide6.QtWidgets import QApplication
    except ImportError as exc:
        raise SystemExit(
            "PySide6 is not installed. Install project dependencies first, "
            "for example with `python3 -m pip install -e .`."
        ) from exc

    from ui.main_window import MainWindow

    app = QApplication(sys.argv)
    icon_path = _find_app_icon()
    if icon_path is not None:
        app_icon = QIcon(str(icon_path))
        app.setWindowIcon(app_icon)
    else:
        app_icon = QIcon()
    window = MainWindow()
    if not app_icon.isNull():
        window.setWindowIcon(app_icon)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
