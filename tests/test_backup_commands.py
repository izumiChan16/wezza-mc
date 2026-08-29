from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class BackupCommandTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="wezza-backup-test-")
        self.root = Path(self.temp_dir.name)
        shutil.copy2(ROOT / "mcctl", self.root / "mcctl")
        (self.root / "runtime" / "backups" / "local").mkdir(parents=True)
        (self.root / "runtime" / "backups" / "offline").mkdir(parents=True)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def archive(self, location: str, name: str = "fixture.tar.zst") -> Path:
        target = self.root / "runtime" / "backups" / location / name
        target.write_bytes(b"fixture")
        return target

    def run_mcctl(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(self.root / "mcctl"), *args],
            cwd=self.root,
            check=False,
            capture_output=True,
            text=True,
        )

    def test_delete_requires_confirmation(self) -> None:
        target = self.archive("offline")
        result = self.run_mcctl("backup-delete", target.name)
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(target.exists())

    def test_delete_alias_removes_one_offline_archive(self) -> None:
        target = self.archive("offline")
        result = self.run_mcctl("backup-delete", target.name, "--confirm")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(target.exists())

    def test_duplicate_name_requires_scope_and_scoped_delete_works(self) -> None:
        local = self.archive("local")
        offline = self.archive("offline")
        result = self.run_mcctl("backup", "delete", local.name, "--confirm")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("local and offline", result.stderr)
        self.assertTrue(local.exists())
        self.assertTrue(offline.exists())

        result = self.run_mcctl("backup", "delete", f"offline/{offline.name}", "--confirm")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(local.exists())
        self.assertFalse(offline.exists())

    def test_backup_list_labels_archive_type(self) -> None:
        self.archive("local", "local-fixture.tar.zst")
        self.archive("offline", "offline-fixture.tar.zst")
        result = self.run_mcctl("backup-list")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("local", result.stdout)
        self.assertIn("offline", result.stdout)


if __name__ == "__main__":
    unittest.main()
