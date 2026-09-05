from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class FrpcCommandTests(unittest.TestCase):
    def run_command(self, command: str, *, config: bool = True,
                    failure: str = "", running: bool = False) -> tuple[subprocess.CompletedProcess[str], list[str]]:
        with tempfile.TemporaryDirectory(prefix="wezza-frpc-test-") as directory:
            root = Path(directory)
            # Source the actual command functions in an isolated copy, without main.
            source = (ROOT / "mcctl").read_text(encoding="utf-8")
            (root / "mcctl").write_text(source.removesuffix('main "$@"\n'), encoding="utf-8")
            if config:
                (root / "frpc.toml").write_text('serverAddr = "example.invalid"\n', encoding="utf-8")
            harness = r'''
source "$TEST_ROOT/mcctl"
load_settings() { EULA=TRUE; PACKWIZ_URL=https://example.org/pack.toml; }
ensure_initialized() { :; }
docker_ready() { :; }
offline_snapshot() { echo snapshot >> "$TEST_ROOT/events"; }
write_deployment_record() { echo deployment >> "$TEST_ROOT/events"; }
sleep() { :; }
docker() { echo healthy; }
service_running() {
  case "$1" in
    minecraft) [[ "$RUNNING" == true ]] ;;
    frpc) [[ "$FAILURE" != exited ]] ;;
    *) return 0 ;;
  esac
}
compose() {
  echo "$*" >> "$TEST_ROOT/events"
  case "$*" in
    'run --rm --no-deps frpc verify -c /etc/frp/frpc.toml') [[ "$FAILURE" != verify ]] ;;
    'up -d --no-deps --force-recreate frpc') [[ "$FAILURE" != up ]] ;;
    'ps -q minecraft') echo minecraft-id ;;
    *) return 0 ;;
  esac
}
run_local_backup() {
  echo local-backup >> "$TEST_ROOT/events"
  [[ "$FAILURE" != local ]]
}
remote_backup_enabled() { return 0; }
run_remote_backup() {
  echo remote-backup >> "$TEST_ROOT/events"
  [[ "$FAILURE" != remote ]]
}
"$@"
'''
            result = subprocess.run(
                ["bash", "-c", harness, "test", *command.split()],
                env={**os.environ, "TEST_ROOT": directory, "FAILURE": failure,
                     "RUNNING": str(running).lower()},
                capture_output=True, text=True, check=False,
            )
            events = root / "events"
            return result, events.read_text().splitlines() if events.exists() else []

    def test_start_rebinds_frpc_after_server_health(self) -> None:
        result, events = self.run_command("command_start")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(events, [
            "snapshot", "stop frpc", "up -d --force-recreate minecraft backup-local",
            "ps -q minecraft", "deployment",
            "run --rm --no-deps frpc verify -c /etc/frp/frpc.toml",
            "up -d --no-deps --force-recreate frpc",
        ])
        self.assertIn("verify the public address", result.stdout)

    def test_tunnel_failures_leave_server_running(self) -> None:
        for failure, config in [("", False), ("verify", True), ("up", True), ("exited", True)]:
            with self.subTest(failure=failure, config=config):
                result, events = self.run_command("command_start", failure=failure, config=config)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("Minecraft and the backup scheduler remain running", result.stderr)
                self.assertNotIn("stop -t 120 backup-local minecraft", events)
                if not config or failure == "verify":
                    self.assertNotIn("up -d --no-deps --force-recreate frpc", events)

    def test_stop_backs_up_before_stopping_tunnel(self) -> None:
        result, events = self.run_command("command_stop", running=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(events[-4:], [
            "local-backup", "remote-backup", "stop frpc",
            "stop -t 120 backup-local minecraft",
        ])

    def test_backup_failures_preserve_tunnel(self) -> None:
        for failure in ("local", "remote"):
            with self.subTest(failure=failure):
                result, events = self.run_command("command_stop", running=True, failure=failure)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn("stop frpc", events)
                self.assertNotIn("stop -t 120 backup-local minecraft", events)

    def test_stop_cleans_orphan_without_config(self) -> None:
        result, events = self.run_command("command_stop", config=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(events, ["stop frpc"])

    def test_skip_remote_still_stops_tunnel(self) -> None:
        result, events = self.run_command("command_stop --skip-remote", running=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("remote-backup", events)
        self.assertIn("stop frpc", events)

    def test_running_server_rejects_start_without_disrupting_tunnel(self) -> None:
        result, events = self.run_command("command_start", running=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(events, [])


if __name__ == "__main__":
    unittest.main()
