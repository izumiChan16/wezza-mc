from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import tarfile
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

    def archive(
        self, location: str, name: str = "fixture.tar.zst", size: int = 7
    ) -> Path:
        target = self.root / "runtime" / "backups" / location / name
        target.write_bytes(b"x" * size)
        return target

    def run_mcctl(
        self, *args: str, extra_env: dict[str, str] | None = None
    ) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        if extra_env:
            env.update(extra_env)
        return subprocess.run(
            [str(self.root / "mcctl"), *args],
            cwd=self.root,
            check=False,
            capture_output=True,
            text=True,
            env=env,
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

    def test_batch_delete_deduplicates_and_preserves_unselected_archives(self) -> None:
        first = self.archive("offline", "first.tar.zst")
        second = self.archive("offline", "second.tar.zst")
        kept = self.archive("offline", "kept.tar.zst")
        result = self.run_mcctl(
            "backup", "delete", f"offline/{first.name}", second.name,
            first.name, "--confirm",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(first.exists())
        self.assertFalse(second.exists())
        self.assertTrue(kept.exists())
        self.assertIn("Deleted 2 archive(s)", result.stdout)

    def test_batch_preflight_rejects_missing_path_and_symlink_before_deleting(self) -> None:
        target = self.archive("offline")
        link = target.with_name("link.tar.zst")
        link.symlink_to(target)
        for invalid in ("missing.tar.zst", "../fixture.tar.zst", "offline/link.tar.zst"):
            with self.subTest(invalid=invalid):
                result = self.run_mcctl("backup", "delete", target.name, invalid, "--confirm")
                self.assertNotEqual(result.returncode, 0)
                self.assertTrue(target.exists())

    def test_batch_preflight_preserves_all_when_scheduler_runs(self) -> None:
        offline = self.archive("offline", "offline.tar.zst")
        local = self.archive("local", "local.tar.zst")
        fake_bin = self.root / "fake-bin"
        fake_bin.mkdir()
        docker = fake_bin / "docker"
        docker.write_text(
            "#!/usr/bin/env bash\n"
            "if [[ $1 == info ]]; then exit 0; fi\n"
            "printf 'backup-local\\n'\n",
            encoding="utf-8",
        )
        docker.chmod(0o755)
        result = self.run_mcctl(
            "backup", "delete", f"offline/{offline.name}", f"local/{local.name}",
            "--confirm", extra_env={"PATH": f"{fake_bin}:{os.environ['PATH']}"},
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("No archives were deleted", result.stderr)
        self.assertTrue(offline.exists())
        self.assertTrue(local.exists())

    def test_batch_reports_partial_deletion_on_filesystem_failure(self) -> None:
        first = self.archive("offline", "first.tar.zst")
        second = self.archive("offline", "second.tar.zst")
        third = self.archive("offline", "third.tar.zst")
        fake_bin = self.root / "fake-bin"
        fake_bin.mkdir()
        rm = fake_bin / "rm"
        rm.write_text(
            "#!/usr/bin/env bash\n"
            "if [[ $* == *second.tar.zst* ]]; then exit 1; fi\n"
            "exec /bin/rm \"$@\"\n",
            encoding="utf-8",
        )
        rm.chmod(0o755)
        result = self.run_mcctl(
            "backup", "delete", first.name, second.name, third.name, "--confirm",
            extra_env={"PATH": f"{fake_bin}:{os.environ['PATH']}"},
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Deleted 1 of 3", result.stderr)
        self.assertFalse(first.exists())
        self.assertTrue(second.exists())
        self.assertTrue(third.exists())

    def test_backup_list_reports_category_and_total_usage(self) -> None:
        self.archive("local", "local-size.tar.zst", size=1024)
        self.archive("offline", "offline-size.tar.zst", size=2048)
        result = self.run_mcctl("backup-list")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertRegex(result.stdout, r"local\s+1 archive\(s\)\s+1\.0 KiB")
        self.assertRegex(result.stdout, r"offline\s+1 archive\(s\)\s+2\.0 KiB")
        self.assertRegex(result.stdout, r"total\s+2 archive\(s\)\s+3\.0 KiB")
        self.assertIn("1.0 KiB  local-size.tar.zst", result.stdout)
        self.assertIn("2.0 KiB  offline-size.tar.zst", result.stdout)

    def test_restore_records_provenance_and_removes_stale_containers(self) -> None:
        data_world = self.root / "runtime" / "data" / "world"
        data_world.mkdir(parents=True)
        (data_world / "level.dat").write_bytes(b"old-world")

        source = self.root / "archive-source"
        source_world = source / "world"
        source_world.mkdir(parents=True)
        (source_world / "level.dat").write_bytes(b"restored-world")
        archive = self.root / "runtime" / "backups" / "offline" / "recovery.tar.gz"
        with tarfile.open(archive, "w:gz") as handle:
            handle.add(source, arcname=".")

        fake_bin = self.root / "fake-bin"
        fake_bin.mkdir()
        docker_log = self.root / "docker.log"
        fake_docker = fake_bin / "docker"
        fake_docker.write_text(
            "#!/usr/bin/env bash\n"
            "if [[ $1 == info ]]; then exit 0; fi\n"
            "printf '%s\\n' \"$*\" >> \"$FAKE_DOCKER_LOG\"\n",
            encoding="utf-8",
        )
        fake_docker.chmod(0o755)

        result = self.run_mcctl(
            "restore",
            "offline/recovery.tar.gz",
            "--confirm",
            extra_env={
                "PATH": f"{fake_bin}:{os.environ['PATH']}",
                "FAKE_DOCKER_LOG": str(docker_log),
            },
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            (self.root / "runtime" / "data" / "world" / "level.dat").read_bytes(),
            b"restored-world",
        )
        self.assertEqual(
            len(list((self.root / "runtime").glob("data.pre-restore.*"))), 1
        )
        records = list((self.root / "runtime" / "restore-history").glob("restore-*.txt"))
        self.assertEqual(len(records), 1)
        self.assertIn("archive_id=offline/recovery.tar.gz", records[0].read_text())
        self.assertIn("rm -sf minecraft backup-local", docker_log.read_text())


if __name__ == "__main__":
    unittest.main()
