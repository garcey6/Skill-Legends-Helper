"""Release packaging tests that do not require PyInstaller."""
from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from tools.build_release import (
    APP_NAME,
    collect_release_files,
    sha256_file,
    write_checksum,
)


class ReleaseFilesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        for relative in (
            "data/schools.json",
            "data/recognize/layout.json",
            "data/art/hero.png",
            "data/guides/demo.md",
            "data/settings.json",
            "data/server_url.txt",
            "data/overlay_position.json",
            "data/meta_stats.json",
            "data/captures/last.png",
            "data/uploads/clip.png",
            "data/source/raw.xlsx",
            "static/index.html",
            "README.md",
            "LICENSE",
            "CHANGELOG.md",
            "docs/USER_GUIDE.md",
            "docs/superpowers/plans/ignored.md",
            "samples/draft_001.png",
            "tests/test_x.py",
            ".git/config",
        ):
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("x", encoding="utf-8")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_collects_runtime_data_and_static_only(self) -> None:
        files = collect_release_files(self.root)
        names = {item.arcname for item in files}

        self.assertIn("data/schools.json", names)
        self.assertIn("data/recognize/layout.json", names)
        self.assertIn("data/art/hero.png", names)
        self.assertIn("data/guides/demo.md", names)
        self.assertIn("static/index.html", names)
        self.assertIn("README.md", names)
        self.assertIn("LICENSE", names)
        self.assertIn("docs/USER_GUIDE.md", names)

        for forbidden in (
            "data/settings.json",
            "data/server_url.txt",
            "data/overlay_position.json",
            "data/meta_stats.json",
            "data/captures/last.png",
            "data/uploads/clip.png",
            "data/source/raw.xlsx",
            "docs/superpowers/plans/ignored.md",
            "samples/draft_001.png",
            "tests/test_x.py",
            ".git/config",
        ):
            self.assertNotIn(forbidden, names)

    def test_arcnames_are_unique_and_use_forward_slashes(self) -> None:
        files = collect_release_files(self.root)
        arcnames = [item.arcname for item in files]
        self.assertEqual(len(arcnames), len(set(arcnames)))
        self.assertTrue(all("\\" not in name for name in arcnames))
        self.assertTrue(all(not name.startswith("/") for name in arcnames))

    def test_missing_root_is_rejected(self) -> None:
        with self.assertRaises(FileNotFoundError):
            collect_release_files(self.root / "missing")

    def test_sha256_file_matches_hashlib(self) -> None:
        path = self.root / "data" / "schools.json"
        expected = hashlib.sha256(path.read_bytes()).hexdigest()
        self.assertEqual(sha256_file(path), expected)

    def test_write_checksum_uses_standard_sha256sum_shape(self) -> None:
        archive = self.root / "release.zip"
        archive.write_bytes(b"zip-bytes")
        checksum = write_checksum(archive)
        digest = hashlib.sha256(b"zip-bytes").hexdigest()
        self.assertEqual(checksum.read_text(encoding="ascii"), f"{digest}  release.zip\n")


class AppNameTest(unittest.TestCase):
    def test_app_name_is_ascii_for_windows_launchers(self) -> None:
        self.assertTrue(APP_NAME.isascii())
        self.assertNotIn(" ", APP_NAME)


if __name__ == "__main__":
    unittest.main()
