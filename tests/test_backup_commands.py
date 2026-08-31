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
