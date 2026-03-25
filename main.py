from __future__ import annotations

from pathlib import Path
import sys


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
    icon_path = Path(__file__).resolve().parent / "android-logo.ico"
    if icon_path.exists():
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
