from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class McctlMenuTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="wezza-menu-test-")
        self.root = Path(self.temp_dir.name)
        shutil.copy2(ROOT / "mcctl", self.root / "mcctl")
        (self.root / "runtime" / "backups" / "local").mkdir(parents=True)
        (self.root / "runtime" / "backups" / "offline").mkdir(parents=True)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def run_mcctl(
        self,
        *args: str,
        menu_input: str | None = None,
        extra_env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["MCCTL_MENU_NO_PAUSE"] = "true"
        if extra_env:
            env.update(extra_env)
        return subprocess.run(
            [str(self.root / "mcctl"), *args],
            cwd=self.root,
            check=False,
            capture_output=True,
            text=True,
            input=menu_input,
            env=env,
        )

    def archive(self, name: str = "fixture.tar.zst") -> Path:
        target = self.root / "runtime" / "backups" / "offline" / name
        target.write_bytes(b"fixture")
        return target

    def test_non_interactive_bare_command_shows_short_help(self) -> None:
        result = self.run_mcctl()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("./mcctl menu", result.stdout)
        self.assertNotIn("world reset --seed", result.stdout)

    def test_plain_menu_reports_missing_setup_and_quits(self) -> None:
        result = self.run_mcctl("menu", "--plain", menu_input="q\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("本机配置", result.stdout)
        self.assertIn("缺少 .env", result.stdout)
        self.assertIn("主菜单", result.stderr)

    def test_help_all_keeps_advanced_commands_discoverable(self) -> None:
        result = self.run_mcctl("help", "--all")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("world reset --seed", result.stdout)
        self.assertIn("mod publish small", result.stdout)

    def test_dashboard_reports_healthy_services_from_one_compose_snapshot(self) -> None:
        tools_dir = self.root / "tools"
        tools_dir.mkdir()
        shutil.copy2(ROOT / "tools" / "world_control.py", tools_dir)
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
        for name in ("rcon_password.txt", "restic_password.txt", "aws_credentials"):
            (secrets / name).write_text("test-only\n", encoding="utf-8")

        fake_bin = self.root / "fake-bin"
        fake_bin.mkdir()
        fake_docker = fake_bin / "docker"
        fake_docker.write_text(
            "#!/usr/bin/env bash\n"
            "if [[ $1 == info ]]; then exit 0; fi\n"
            "if [[ $1 == inspect ]]; then printf 'healthy\\n'; exit 0; fi\n"
            "if [[ $1 == compose && $* == *'ps --status running --services'* ]]; then\n"
            "  printf 'minecraft\\nminecraft-staging\\n'; exit 0\n"
            "fi\n"
            "if [[ $1 == compose && $* == *'ps -q minecraft-staging'* ]]; then\n"
            "  printf 'staging-id\\n'; exit 0\n"
            "fi\n"
            "if [[ $1 == compose && $* == *'ps -q minecraft'* ]]; then\n"
            "  printf 'production-id\\n'; exit 0\n"
            "fi\n"
            "exit 0\n",
            encoding="utf-8",
        )
        fake_docker.chmod(0o755)

        result = self.run_mcctl(
            "menu",
            "--plain",
            menu_input="q\n",
            extra_env={"PATH": f"{fake_bin}:{os.environ['PATH']}"},
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Docker        可用", result.stdout)
        self.assertIn("正式服务器    健康", result.stdout)
        self.assertIn("测试服务器    健康", result.stdout)
        self.assertIn("查看正式服务器详情", result.stdout)

    def test_dashboard_reports_combined_local_backup_usage(self) -> None:
        (self.root / "runtime" / "backups" / "local" / "local.tar.zst").write_bytes(
            b"x" * 1024
        )
        (self.root / "runtime" / "backups" / "offline" / "offline.tar.zst").write_bytes(
            b"x" * 2048
        )
        result = self.run_mcctl("menu", "--plain", menu_input="q\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("本机备份      2 个 · 3.0 KiB", result.stdout)

    def test_menu_delete_defaults_to_no_and_accepts_n_case_insensitively(self) -> None:
        target = self.archive()
        for answer in ("", "n", "N"):
            with self.subTest(answer=answer or "empty"):
                result = self.run_mcctl(
                    "menu",
                    "--plain",
                    menu_input=f"6\n7\n1\n{answer}\nq\nq\n",
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertTrue(target.exists())
                self.assertIn("没有进行任何更改", result.stdout)

    def test_menu_delete_accepts_y_case_insensitively_and_stays_in_category(self) -> None:
        for answer in ("y", "Y"):
            with self.subTest(answer=answer):
                target = self.archive()
                result = self.run_mcctl(
                    "menu",
                    "--plain",
                    menu_input=f"6\n7\n1\n{answer}\nq\nq\n",
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertFalse(target.exists())
                self.assertIn("Backup deleted", result.stdout)
                self.assertGreaterEqual(result.stderr.count("世界与备份 ·"), 2)

    def test_menu_delete_reprompts_after_an_invalid_confirmation(self) -> None:
        target = self.archive()
        result = self.run_mcctl(
            "menu",
            "--plain",
            menu_input="6\n7\n1\nmaybe\nY\nq\nq\n",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(target.exists())
        self.assertIn("请输入 Y 或 N", result.stderr)

    def test_successful_server_lifecycle_action_returns_to_dashboard(self) -> None:
        tools_dir = self.root / "tools"
        tools_dir.mkdir()
        shutil.copy2(ROOT / "tools" / "world_control.py", tools_dir)
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
        for name in ("rcon_password.txt", "restic_password.txt", "aws_credentials"):
            (secrets / name).write_text("test-only\n", encoding="utf-8")

        fake_bin = self.root / "fake-bin"
        fake_bin.mkdir()
        fake_docker = fake_bin / "docker"
        fake_docker.write_text(
            "#!/usr/bin/env bash\n"
            "if [[ $1 == info ]]; then exit 0; fi\n"
            "if [[ $1 == inspect ]]; then printf 'healthy\\n'; exit 0; fi\n"
            "if [[ $1 == compose && $* == *'ps --status running --services'* ]]; then\n"
            "  exit 0\n"
            "fi\n"
            "if [[ $1 == compose && $* == *'ps -q minecraft'* ]]; then\n"
            "  printf 'production-id\\n'; exit 0\n"
            "fi\n"
            "exit 0\n",
            encoding="utf-8",
        )
        fake_docker.chmod(0o755)

        result = self.run_mcctl(
            "menu",
            "--plain",
            menu_input="2\n1\ny\n9\n",
            extra_env={"PATH": f"{fake_bin}:{os.environ['PATH']}"},
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("操作已成功完成", result.stdout)
        self.assertEqual(result.stderr.count("\n正式服务器\n"), 1)
        self.assertGreaterEqual(result.stdout.count("Wezza MC 管理面板"), 2)

    def test_doctor_fails_actionably_in_an_uninitialized_copy(self) -> None:
        result = self.run_mcctl("doctor")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("FAIL  .env", result.stdout)
        self.assertIn("'./mcctl init'", result.stdout)


if __name__ == "__main__":
    unittest.main()
