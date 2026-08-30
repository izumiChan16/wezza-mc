from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class StagingCommandTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="wezza-stage-command-test-")
        self.root = Path(self.temp_dir.name)
        shutil.copy2(ROOT / "mcctl", self.root / "mcctl")
        tools = self.root / "tools"
        tools.mkdir()
        shutil.copy2(ROOT / "tools" / "world_control.py", tools / "world_control.py")
        shutil.copy2(
            ROOT / "tools" / "staging_session.py", tools / "staging_session.py"
        )
        (tools / "validate_pack.py").write_text(
            "#!/usr/bin/env python3\nraise SystemExit(0)\n", encoding="utf-8"
        )

        (self.root / "pack").mkdir()
        (self.root / "pack" / "pack.toml").write_text(
            'name = "test"\nversion = "1.0.0"\n', encoding="utf-8"
        )
        (self.root / "runtime" / "data" / "world").mkdir(parents=True)
        (self.root / "runtime" / "data" / "world" / "level.dat").write_bytes(
            b"production-world"
        )
        (self.root / "runtime" / "backups" / "local").mkdir(parents=True)
        (self.root / "runtime" / "backups" / "offline").mkdir(parents=True)
        (self.root / "runtime" / "staging").mkdir(parents=True)
        (self.root / ".env").write_text(
            "EULA=TRUE\n"
            "PACKWIZ_URL=https://example.com/pack.toml\n"
            "MC_BIND_IP=127.0.0.1\n"
            "MC_PORT=25565\n"
            "WORLD_NAME=world\n"
            "WORLD_SEED=\n",
            encoding="utf-8",
        )
        secrets = self.root / "secrets"
        secrets.mkdir()
        (secrets / "rcon_password.txt").write_text("test-only\n", encoding="utf-8")

        fake_bin = self.root / "fake-bin"
        fake_bin.mkdir()
        fake_docker = fake_bin / "docker"
        fake_docker.write_text(
            "#!/usr/bin/env bash\n"
            "if [[ $1 == info ]]; then exit 0; fi\n"
            "if [[ $1 == inspect ]]; then printf 'healthy\\n'; exit 0; fi\n"
            "if [[ $1 == compose && $* == *'ps --status running --services'* ]]; then\n"
            "  [[ ${FAKE_PRODUCTION_RUNNING:-false} == true ]] && printf 'minecraft\\n'\n"
            "  [[ ${FAKE_STAGING_RUNNING:-false} == true ]] && printf 'minecraft-staging\\n'\n"
            "  exit 0\n"
            "fi\n"
            "if [[ $1 == compose && $* == *'ps -q minecraft-staging'* ]]; then\n"
            "  printf 'staging-id\\n'; exit 0\n"
            "fi\n"
            "exit 0\n",
            encoding="utf-8",
        )
        fake_docker.chmod(0o755)
        self.env = os.environ.copy()
        self.env["PATH"] = f"{fake_bin}:{self.env['PATH']}"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def run_mcctl(
        self,
        *args: str,
        staging_running: bool = False,
        menu_input: str | None = None,
    ) -> subprocess.CompletedProcess[str]:
        env = self.env.copy()
        env["FAKE_STAGING_RUNNING"] = "true" if staging_running else "false"
        env["MCCTL_MENU_NO_PAUSE"] = "true"
        return subprocess.run(
            [str(self.root / "mcctl"), *args],
            cwd=self.root,
            check=False,
            capture_output=True,
            text=True,
            input=menu_input,
            env=env,
        )

    def offline_backups(self) -> list[Path]:
        return list(
            (self.root / "runtime" / "backups" / "offline").glob("*.tar.zst")
        )

    def test_rebuild_reuses_backup_and_finish_deletes_only_that_backup(self) -> None:
        result = self.run_mcctl("stage", "start")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(self.offline_backups()), 1)
        self.assertTrue((self.root / "runtime" / "staging" / "SESSION").is_file())
        self.assertTrue(
            (self.root / "runtime" / "staging" / "data" / "world" / "level.dat").is_file()
        )

        result = self.run_mcctl("stage", "resume")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(self.offline_backups()), 1)

        (self.root / "pack" / "candidate.txt").write_text(
            "new candidate\n", encoding="utf-8"
        )
        result = self.run_mcctl("stage", "rebuild", staging_running=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(self.offline_backups()), 1)

        result = self.run_mcctl(
            "menu",
            "--plain",
            staging_running=True,
            menu_input="3\n1\n\n3\nq\n",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("删除本次测试专用备份吗？ [Y/n]", result.stderr)
        self.assertIn("发布已留到稍后", result.stdout)
        self.assertEqual(self.offline_backups(), [])
        self.assertFalse((self.root / "runtime" / "staging" / "SESSION").exists())
        self.assertFalse((self.root / "runtime" / "staging" / "data").exists())
        self.assertTrue(
            (self.root / "runtime" / "data" / "world" / "level.dat").is_file()
        )
        self.assertTrue(
            (self.root / "runtime" / "staging" / "ACCEPTED_PACK_SHA256").is_file()
        )

    def test_failed_test_discards_copy_but_keeps_backup_and_candidate(self) -> None:
        result = self.run_mcctl("stage", "start")
        self.assertEqual(result.returncode, 0, result.stderr)
        backups = self.offline_backups()
        self.assertEqual(len(backups), 1)
        (self.root / "pack" / "candidate.txt").write_text(
            "keep this change\n", encoding="utf-8"
        )

        result = self.run_mcctl("stage", "discard", "--confirm")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(backups[0].is_file())
        self.assertTrue((self.root / "pack" / "candidate.txt").is_file())
        self.assertFalse((self.root / "runtime" / "staging" / "data").exists())
        self.assertFalse((self.root / "runtime" / "staging" / "SESSION").exists())


if __name__ == "__main__":
    unittest.main()
