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
offline_snapshot() { echo snapshot >> "$TEST_ROOT/events"; [[ "$FAILURE" != local ]]; }
write_deployment_record() { echo deployment >> "$TEST_ROOT/events"; }
sleep() { :; }
docker() {
  if [[ "$*" == *ExitCode* ]]; then
    [[ "$FAILURE" == unclean ]] && echo 137 || echo 0
  else echo healthy; fi
}
backup_control() {
  echo "control $*" >> "$TEST_ROOT/events"
  [[ "$FAILURE" != preflight || "$1" != remote-check ]]
}
service_running() {
  case "$1" in
    minecraft) [[ "$RUNNING" == true ]] ;;
    frpc) [[ "$FAILURE" != exited ]] ;;
    *) return 0 ;;
  esac
}
production_running_checked() { service_running minecraft; }
compose() {
  echo "$*" >> "$TEST_ROOT/events"
  case "$*" in
    'run --rm --no-deps frpc verify -c /etc/frp/frpc.toml') [[ "$FAILURE" != verify ]] ;;
    'up -d --no-deps --force-recreate frpc') [[ "$FAILURE" != up ]] ;;
    'ps -q minecraft') echo minecraft-id ;;
    'stop -t 120 minecraft') RUNNING=false ;;
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
            "control remote-check online", "control session-stop",
            "snapshot", "stop frpc backup-local", "up -d --force-recreate minecraft",
            "ps -q minecraft", "deployment", "control session-start off on",
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

    def test_stop_backs_up_after_stopping_tunnel(self) -> None:
        result, events = self.run_command("command_stop", running=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(events[-5:], [
            "stop frpc", "stop -t 120 minecraft", "snapshot",
            "control record local 0 Shutdown snapshot completed", "remote-backup",
        ])

    def test_backup_failures_leave_server_stopped(self) -> None:
        for failure in ("local", "remote"):
            with self.subTest(failure=failure):
                result, events = self.run_command("command_stop", running=True, failure=failure)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("stop -t 120 minecraft", events)
                self.assertIn("server remains stopped", result.stderr)
                if failure == "local":
                    self.assertNotIn("remote-backup", events)

    def test_all_start_backup_combinations(self) -> None:
        for local in ("off", "on"):
            for remote in ("off", "on"):
                with self.subTest(local=local, remote=remote):
                    result, events = self.run_command(
                        f"command_start --local-auto={local} --s3-auto={remote}")
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertIn(f"control session-start {local} {remote}", events)
                    self.assertEqual("control remote-check online" in events, remote == "on")
                    self.assertNotIn("up -d --force-recreate minecraft backup-local", events)

    def test_preflight_failure_never_starts_server(self) -> None:
        result, events = self.run_command("command_start", failure="preflight")
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("snapshot", events)
        self.assertNotIn("stop frpc backup-local", events)

    def test_failed_start_snapshot_never_starts_server(self) -> None:
        result, events = self.run_command("command_start", failure="local")
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("up -d --force-recreate minecraft", events)

    def test_restart_checks_s3_before_stopping(self) -> None:
        result, events = self.run_command("command_restart", running=True, failure="preflight")
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("stop frpc", events)

    def test_failed_shutdown_backup_prevents_restart(self) -> None:
        result, events = self.run_command("command_restart", running=True, failure="remote")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("stop -t 120 minecraft", events)
        self.assertNotIn("up -d --force-recreate minecraft", events)

    def test_unclean_shutdown_refuses_final_backups(self) -> None:
        result, events = self.run_command("command_stop", running=True, failure="unclean")
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("snapshot", events)
        self.assertNotIn("remote-backup", events)

    def test_stop_cleans_orphan_without_config(self) -> None:
        result, events = self.run_command("command_stop", config=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(events, ["control session-stop", "stop frpc backup-local"])

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
