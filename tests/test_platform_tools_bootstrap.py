from __future__ import annotations

from pathlib import Path
import sys
import stat
import tempfile
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.platform_tools_bootstrap import PlatformToolsBootstrapper


class PlatformToolsBootstrapperTests(unittest.TestCase):
    def test_download_and_install_extracts_archive_for_linux(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir_name:
            temp_dir = Path(temp_dir_name)
            app_root = temp_dir / "app"
            archive_path = temp_dir / "platform-tools-linux.zip"
            self._build_archive(
                archive_path,
                {
                    "platform-tools/adb": "#!/bin/sh\necho adb\n",
                    "platform-tools/fastboot": "#!/bin/sh\necho fastboot\n",
                    "platform-tools/source.properties": "Pkg.Revision=99.0.0\n",
                },
            )

            bootstrapper = PlatformToolsBootstrapper(app_root=app_root)
            result = bootstrapper.download_and_install(
                platform_key="linux",
                download_url=archive_path.as_uri(),
            )

            self.assertTrue(result.success)
            adb_path = app_root / "resources" / "platform-tools" / "linux" / "adb"
            self.assertTrue(adb_path.exists())
            self.assertTrue(adb_path.stat().st_mode & stat.S_IXUSR)
            self.assertTrue((adb_path.parent / "fastboot").exists())

    def test_ensure_present_skips_download_when_adb_exists(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir_name:
            app_root = Path(temp_dir_name) / "app"
            adb_path = app_root / "resources" / "platform-tools" / "windows" / "adb.exe"
            adb_path.parent.mkdir(parents=True, exist_ok=True)
            adb_path.write_text("binary", encoding="utf-8")

            bootstrapper = PlatformToolsBootstrapper(app_root=app_root)
            result = bootstrapper.ensure_present(platform_key="windows")

            self.assertTrue(result.success)
            self.assertFalse(result.downloaded)

    def _build_archive(self, archive_path: Path, files: dict[str, str]) -> None:
        with zipfile.ZipFile(archive_path, "w") as archive:
            for name, content in files.items():
                archive.writestr(name, content)


if __name__ == "__main__":
    unittest.main()
