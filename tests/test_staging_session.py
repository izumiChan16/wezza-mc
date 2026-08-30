from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "staging_session.py"
PACK_SHA = "a" * 64


class StagingSessionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="wezza-stage-session-test-")
        self.root = Path(self.temp_dir.name)
        (self.root / "runtime" / "staging").mkdir(parents=True)
        (self.root / "runtime" / "backups" / "local").mkdir(parents=True)
        (self.root / "runtime" / "backups" / "offline").mkdir(parents=True)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def run_tool(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(TOOL), *args, "--root", str(self.root)],
            check=False,
            capture_output=True,
            text=True,
        )

    def record(self, status: str, backup_id: str = "") -> subprocess.CompletedProcess[str]:
        args = [
            "record",
            "--pack-sha",
            PACK_SHA,
            "--backup-status",
            status,
        ]
        if backup_id:
            args.extend(("--backup-id", backup_id))
        return self.run_tool(*args)

    def test_tracked_backup_is_deleted_only_when_identity_matches(self) -> None:
        archive = self.root / "runtime" / "backups" / "local" / "test.tar.zst"
        archive.write_bytes(b"backup")
        result = self.record("tracked", "local/test.tar.zst")
        self.assertEqual(result.returncode, 0, result.stderr)

        result = self.run_tool("inspect")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(f"active|{PACK_SHA}|tracked|local/test.tar.zst|", result.stdout)

        result = self.run_tool("delete-backup")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(archive.exists())

    def test_changed_tracked_backup_is_kept(self) -> None:
        archive = self.root / "runtime" / "backups" / "offline" / "test.tar.zst"
        archive.write_bytes(b"backup")
        result = self.record("tracked", "offline/test.tar.zst")
        self.assertEqual(result.returncode, 0, result.stderr)
        archive.write_bytes(b"changed backup")

        result = self.run_tool("delete-backup")
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertTrue(archive.exists())
        self.assertIn("changed and was kept", result.stdout)

    def test_untracked_backup_is_never_deleted(self) -> None:
        archive = self.root / "runtime" / "backups" / "local" / "test.tar.zst"
        archive.write_bytes(b"backup")
        result = self.record("untracked", "local/test.tar.zst")
        self.assertEqual(result.returncode, 0, result.stderr)
        result = self.run_tool("delete-backup")
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertTrue(archive.exists())
        self.assertIn("not uniquely tracked", result.stdout)

    def test_symlinked_backup_directory_is_rejected(self) -> None:
        real_directory = self.root / "outside-backups"
        real_directory.mkdir()
        (real_directory / "test.tar.zst").write_bytes(b"backup")
        local_directory = self.root / "runtime" / "backups" / "local"
        local_directory.rmdir()
        local_directory.symlink_to(real_directory, target_is_directory=True)

        result = self.record("tracked", "local/test.tar.zst")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("symlinked backup directories", result.stderr)
        self.assertTrue((real_directory / "test.tar.zst").is_file())

    def test_cleanup_removes_only_current_and_previous_staging_data(self) -> None:
        staging = self.root / "runtime" / "staging"
        (staging / "data" / "world").mkdir(parents=True)
        (staging / "data" / "world" / "level.dat").write_bytes(b"world")
        (staging / "data.previous.123" / "world").mkdir(parents=True)
        (staging / "data.previous.123" / "world" / "level.dat").write_bytes(b"old")
        accepted = staging / "ACCEPTED_PACK_SHA256"
        accepted.write_text(PACK_SHA + "\n", encoding="utf-8")
        production = self.root / "runtime" / "data" / "world"
        production.mkdir(parents=True)
        (production / "level.dat").write_bytes(b"production")

        result = self.run_tool("usage")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(result.stdout.startswith("2|"))
        result = self.run_tool("cleanup-data")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((staging / "data").exists())
        self.assertFalse((staging / "data.previous.123").exists())
        self.assertTrue(accepted.exists())
        self.assertTrue((production / "level.dat").exists())

    def test_pack_hash_can_be_updated_without_changing_backup_identity(self) -> None:
        archive = self.root / "runtime" / "backups" / "local" / "test.tar.zst"
        archive.write_bytes(b"backup")
        self.assertEqual(
            self.record("tracked", "local/test.tar.zst").returncode, 0
        )
        new_sha = "b" * 64
        result = self.run_tool("update-pack", "--pack-sha", new_sha)
        self.assertEqual(result.returncode, 0, result.stderr)
        result = self.run_tool("inspect")
        self.assertIn(f"active|{new_sha}|tracked|local/test.tar.zst|", result.stdout)
        self.assertTrue(archive.exists())


if __name__ == "__main__":
    unittest.main()
