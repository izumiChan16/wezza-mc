from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("backup_control", ROOT / "tools" / "backup_control.py")
backup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backup)


def snapshot(name: str, day: int, *tags: str) -> dict:
    return {"id": name, "time": f"2026-09-{day:02d}T12:00:00Z", "tags": ["wezza-mc", *tags]}


class BackupControlTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="wezza-backup-control-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "secrets").mkdir()
        (self.root / "secrets" / "aws_credentials").write_text(
            "[default]\naws_access_key_id=test-only-id\naws_secret_access_key=test-only-secret\n")
        self.env = patch.dict(os.environ, {
            "RESTIC_REPOSITORY": "s3:http://127.0.0.1:5246/WezzaMC/wezza-mc",
            "AWS_DEFAULT_REGION": "us-east-1", "RESTIC_HOSTNAME": "test-host",
            "S3_ONLINE_LIMIT_KIB": "5120", "S3_TARGET_BYTES": "80000000000",
            "S3_HIGH_WATER_BYTES": "90000000000", "S3_CAPACITY_BYTES": "100000000000",
        })
        self.env.start()
        self.addCleanup(self.env.stop)

    def remote(self, online: bool = True):
        return backup.Remote(self.root, online)

    def test_path_style_preserves_bucket_case(self) -> None:
        s3 = backup.S3(self.root)
        self.assertEqual(s3.bucket, "WezzaMC")
        self.assertEqual(s3.prefix, "wezza-mc/")
        response = MagicMock()
        response.__enter__.return_value.read.side_effect = [b"ok", b""]
        opener = MagicMock()
        opener.open.return_value = response
        with patch.object(backup.urllib.request, "build_opener", return_value=opener):
            self.assertEqual(s3.request("GET", "config"), b"ok")
        request = opener.open.call_args.args[0]
        self.assertEqual(request.full_url, "http://127.0.0.1:5246/WezzaMC/config")
        self.assertIn("SignedHeaders=host;x-amz-content-sha256;x-amz-date", request.get_header("Authorization"))
        self.assertNotIn("test-only-secret", request.get_header("Authorization"))

    def test_inventory_counts_all_pages_and_other_prefixes(self) -> None:
        s3 = backup.S3(self.root)
        pages = [b'''<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">
<Contents><Key>wezza-mc/data/a</Key><Size>10</Size></Contents>
<IsTruncated>true</IsTruncated><NextContinuationToken>token +/</NextContinuationToken></ListBucketResult>''',
                 b'''<ListBucketResult><Contents><Key>other/data</Key><Size>7</Size></Contents>
<IsTruncated>false</IsTruncated></ListBucketResult>''']
        with patch.object(s3, "request", side_effect=pages) as request:
            self.assertEqual(s3.usage(), 17)
            self.assertEqual(request.call_args.kwargs["query"]["continuation-token"], "token +/")

    def test_invalid_or_incomplete_inventory_fails_closed(self) -> None:
        for response in (b"<html>web UI</html>", b"<ListBucketResult/>",
                         b"<ListBucketResult><IsTruncated>true</IsTruncated></ListBucketResult>"):
            with self.subTest(response=response):
                s3 = backup.S3(self.root)
                with patch.object(s3, "request", return_value=response), self.assertRaises(backup.BackupError):
                    s3.usage()

    def test_repeated_pagination_token_fails(self) -> None:
        s3 = backup.S3(self.root)
        page = b"<ListBucketResult><IsTruncated>true</IsTruncated><NextContinuationToken>a</NextContinuationToken></ListBucketResult>"
        with patch.object(s3, "request", return_value=page), self.assertRaises(backup.BackupError):
            s3.usage()

    def test_online_and_offline_limits(self) -> None:
        self.assertEqual(self.remote().limit, 5120)
        self.assertEqual(self.remote(False).limit, 0)
        with patch.dict(os.environ, {"S3_ONLINE_LIMIT_KIB": "0"}), self.assertRaises(backup.BackupError):
            self.remote()
        with patch.dict(os.environ, {"S3_TARGET_BYTES": "95000000000"}), self.assertRaises(backup.BackupError):
            self.remote()

    def test_remote_backup_restores_saving_after_upload_failure(self) -> None:
        remote = self.remote()
        calls = []
        with patch.object(remote, "check"), patch.object(remote, "discard_pending"), patch.object(remote, "cleanup"), \
                patch.object(remote, "rcon", side_effect=lambda command: calls.append(command)), \
                patch.object(remote, "restic", side_effect=backup.BackupError("upload failed")):
            with self.assertRaises(backup.BackupError):
                remote.backup()
        self.assertEqual(calls, ["save-off", "save-all flush", "save-on"])

    def test_save_off_failure_still_attempts_save_on(self) -> None:
        remote = self.remote()
        with patch.object(remote, "check"), patch.object(remote, "discard_pending"), patch.object(remote, "cleanup"), \
                patch.object(remote, "restic") as restic, \
                patch.object(remote, "rcon", side_effect=[backup.BackupError("RCON failed"), None]) as rcon:
            with self.assertRaises(backup.BackupError):
                remote.backup()
        self.assertEqual([call.args[0] for call in rcon.call_args_list], ["save-off", "save-on"])
        restic.assert_not_called()

    def test_offline_backup_does_not_call_rcon(self) -> None:
        remote = self.remote(False)
        with patch.object(remote, "check"), patch.object(remote, "discard_pending"), patch.object(remote, "cleanup"), \
                patch.object(remote, "rcon") as rcon, patch.object(remote, "restic", return_value='[ {"id": "completed"} ]') as restic:
            remote.backup()
        rcon.assert_not_called()
        self.assertIn("wezza-mc,session_end", restic.call_args.args)

    def test_failed_inventory_never_turns_off_saving(self) -> None:
        remote = self.remote()
        with patch.object(remote.s3, "usage", side_effect=backup.BackupError("unavailable")), \
                patch.object(remote, "rcon") as rcon, patch.object(remote, "restic") as restic:
            with self.assertRaises(backup.BackupError):
                remote.backup()
        rcon.assert_not_called()
        restic.assert_not_called()

    def test_capacity_cleanup_protects_latest_and_last_shutdown(self) -> None:
        remote = self.remote()
        snapshots = [snapshot("shutdown", 1, "session_end"), snapshot("old", 2), snapshot("latest", 3)]
        with patch.object(remote, "snapshots", return_value=snapshots), \
                patch.object(remote.s3, "usage", side_effect=[95_000_000_000, 95_000_000_000, 79_000_000_000]), \
                patch.object(remote, "prune") as prune, patch.object(remote, "restic") as restic:
            remote.cleanup()
        restic.assert_called_once_with("forget", "old")
        self.assertEqual(prune.call_count, 2)

    def test_protected_snapshots_over_budget_block_upload(self) -> None:
        remote = self.remote()
        with patch.object(remote, "snapshots", return_value=[snapshot("only", 1, "session_end")]), \
                patch.object(remote.s3, "usage", return_value=95_000_000_000), \
                patch.object(remote, "prune"), patch.object(remote, "restic") as restic:
            with self.assertRaises(backup.BackupError):
                remote.cleanup()
        restic.assert_not_called()

    def test_failed_prune_stops_before_forgetting_more(self) -> None:
        remote = self.remote()
        with patch.object(remote, "snapshots", return_value=[snapshot("old", 1), snapshot("new", 2)]), \
                patch.object(remote.s3, "usage", return_value=95_000_000_000), \
                patch.object(remote, "prune", side_effect=backup.BackupError("prune failed")), \
                patch.object(remote, "restic") as restic:
            with self.assertRaises(backup.BackupError):
                remote.cleanup()
        restic.assert_not_called()

    def test_retention_keeps_last_shutdown_even_if_old(self) -> None:
        remote = self.remote()
        snapshots = [snapshot("shutdown", 1, "session_end"), snapshot("old", 2), snapshot("new", 3)]
        def restic(*args, **kwargs):
            if "--dry-run" in args:
                return json.dumps([{"remove": snapshots[:2]}])
            return ""
        with patch.object(remote, "snapshots", return_value=snapshots), \
                patch.object(remote.s3, "usage", return_value=10), patch.object(remote, "prune"), \
                patch.object(remote, "restic", side_effect=restic) as command:
            remote.cleanup(retention=True)
        self.assertIn(unittest.mock.call("forget", "old"), command.call_args_list)
        self.assertNotIn(unittest.mock.call("forget", "shutdown"), command.call_args_list)

    def test_high_water_stops_container_not_only_docker_cli(self) -> None:
        remote = self.remote()
        process = MagicMock()
        process.communicate.side_effect = [subprocess.TimeoutExpired("docker", 5), (None, "")]
        process.poll.return_value = None
        with patch.object(backup.subprocess, "Popen", return_value=process) as popen, \
                patch.object(backup.subprocess, "run") as run, \
                patch.object(remote.s3, "usage", return_value=91_000_000_000):
            with self.assertRaises(backup.BackupError):
                remote.restic("backup", "/data", monitor=True)
        self.assertEqual(run.call_args_list[0].args[0][:4], ["docker", "stop", "-t", "30"])
        self.assertEqual(run.call_args_list[1].args[0][:3], ["docker", "rm", "-f"])
        command = popen.call_args.args[0]
        self.assertEqual(command[command.index("--limit-upload") + 1], "5120")
        self.assertEqual(command[command.index("--limit-download") + 1], "5120")

    def test_existing_repository_is_never_reinitialized(self) -> None:
        remote = self.remote(False)
        with patch.object(remote.s3, "usage", return_value=100), \
                patch.object(remote.s3, "objects", return_value=[("wezza-mc/config", 100)]), \
                patch.object(remote, "check", side_effect=backup.BackupError("wrong password")), \
                patch.object(remote, "restic") as restic:
            with self.assertRaises(backup.BackupError):
                remote.initialize()
        restic.assert_not_called()

    def test_session_start_detaches_without_inheriting_operation_lock(self) -> None:
        with patch.object(backup.subprocess, "Popen") as process:
            process.return_value.pid = 12345
            backup.session_start(self.root, "off", "on")
        state = backup.read_json(backup.control_dir(self.root) / "session.json")
        self.assertEqual((state["local"], state["s3"]), ("off", "on"))
        self.assertTrue(process.call_args.kwargs["close_fds"])
        self.assertTrue(process.call_args.kwargs["start_new_session"])
        self.assertGreater(state["next"], backup.time.time() + 7190)
        self.assertEqual(backup.session_flags(self.root, "stale-id"), {})

    def test_disabled_session_never_spawns_scheduler(self) -> None:
        with patch.object(backup.subprocess, "Popen") as process:
            backup.session_start(self.root, "off", "off")
        process.assert_not_called()
        state = backup.read_json(backup.control_dir(self.root) / "session.json")
        self.assertEqual(backup.session_flags(self.root, state["id"]), {})

    def test_local_manual_backup_is_one_shot(self) -> None:
        with patch.object(backup, "run_container") as run, patch.object(backup, "rcon") as rcon:
            backup.local_backup(self.root)
        command = run.call_args.args[0]
        self.assertEqual(command[-2:], ["backup-local", "now"])
        self.assertIn("--no-deps", command)
        self.assertNotIn("up", command)
        rcon.assert_called_once_with(self.root, "save-on")

    def test_local_failure_restores_saving(self) -> None:
        with patch.object(backup, "run_container", side_effect=backup.BackupError("failed")), \
                patch.object(backup, "rcon") as rcon:
            with self.assertRaises(backup.BackupError):
                backup.local_backup(self.root)
        rcon.assert_called_once_with(self.root, "save-on")

    def test_enable_changes_only_remote_switch_and_protects_env(self) -> None:
        env = self.root / ".env"
        env.write_text("EULA=FALSE\nENABLE_REMOTE_BACKUP=false\nWORLD_NAME=world\n")
        backup.enable_remote(self.root)
        self.assertEqual(env.read_text(), "EULA=FALSE\nENABLE_REMOTE_BACKUP=true\nWORLD_NAME=world\n")
        self.assertEqual(env.stat().st_mode & 0o777, 0o600)

    def test_failed_init_does_not_enable_remote(self) -> None:
        env = self.root / ".env"
        env.write_text("ENABLE_REMOTE_BACKUP=false\n")
        with patch.object(backup.Remote, "initialize", side_effect=backup.BackupError("unavailable")), \
                patch.object(backup.sys, "argv", ["backup_control", "--root", str(self.root), "remote-init"]):
            self.assertEqual(backup.main(), 1)
        self.assertEqual(env.read_text(), "ENABLE_REMOTE_BACKUP=false\n")

    def test_operation_lock_serializes_separate_commands(self) -> None:
        (self.root / "mcctl").write_text((ROOT / "mcctl").read_text().removesuffix('main "$@"\n'))
        import fcntl
        directory = backup.control_dir(self.root)
        directory.mkdir(parents=True)
        with (directory / "operation.lock").open("w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            process = subprocess.Popen(
                ["bash", "-c", 'source "$1/mcctl"; backup_lock; echo acquired', "test", str(self.root)],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                with self.assertRaises(subprocess.TimeoutExpired):
                    process.communicate(timeout=0.2)
                fcntl.flock(lock, fcntl.LOCK_UN)
                stdout, stderr = process.communicate(timeout=5)
                self.assertEqual(process.returncode, 0, stderr)
                self.assertIn("acquired", stdout)
            finally:
                if process.poll() is None:
                    process.kill()
                    process.communicate()

    def test_local_failure_quarantines_only_its_new_archive(self) -> None:
        directory = self.root / "runtime" / "backups" / "local"
        directory.mkdir(parents=True)
        old = directory / "old.tar.zst"
        old.write_bytes(b"previous")
        latest = directory / "latest.tar.zst"
        latest.symlink_to(old.name)
        def fail(command, *args):
            prefix = next(value.split("=", 1)[1] for value in command if value.startswith("BACKUP_NAME="))
            partial = directory / (prefix + "-20260908-120000.tar.zst")
            partial.write_bytes(b"partial")
            latest.unlink()
            latest.symlink_to(partial.name)
            raise backup.BackupError("compression failed")
        with patch.object(backup, "run_container", side_effect=fail), patch.object(backup, "rcon"):
            with self.assertRaises(backup.BackupError):
                backup.local_backup(self.root)
        self.assertEqual(old.read_bytes(), b"previous")
        self.assertEqual(os.readlink(latest), old.name)
        self.assertEqual(len(list(directory.glob("*.failed"))), 1)

    def test_partial_s3_snapshot_is_not_promoted(self) -> None:
        remote = self.remote()
        with patch.object(remote, "check"), patch.object(remote, "discard_pending"), \
                patch.object(remote, "cleanup"), patch.object(remote, "rcon"), \
                patch.object(remote, "restic", side_effect=backup.BackupError("exit 3")) as restic:
            with self.assertRaises(backup.BackupError):
                remote.backup()
        self.assertEqual(len(restic.call_args_list), 1)
        args = restic.call_args.args
        self.assertIn("wezza-mc-pending", args)
        self.assertNotIn("wezza-mc", args)

    def test_pending_cleanup_does_not_touch_successful_snapshots(self) -> None:
        remote = self.remote()
        def restic(*args, **kwargs):
            return '[{"id":"incomplete"}]' if args[0] == "snapshots" else ""
        with patch.object(remote, "restic", side_effect=restic) as command, patch.object(remote, "prune"):
            remote.discard_pending()
        self.assertIn("wezza-mc-pending", command.call_args_list[0].args)
        self.assertEqual(command.call_args_list[1].args, ("forget", "incomplete"))

    def test_snapshot_order_uses_timezones(self) -> None:
        older = {"id": "older", "time": "2026-09-08T08:00:00+08:00", "tags": []}
        newer = {"id": "newer", "time": "2026-09-08T07:00:00Z", "tags": []}
        self.assertEqual(backup.Remote.protected([older, newer]), {"newer"})

    def test_docker_failure_is_not_treated_as_stopped(self) -> None:
        (self.root / "mcctl").write_text((ROOT / "mcctl").read_text().removesuffix('main "$@"\n'))
        harness = '''source "$1/mcctl"
compose() { return 1; }
if production_running_checked; then echo running; else echo stopped; fi
'''
        result = subprocess.run(["bash", "-c", harness, "test", str(self.root)], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("stopped", result.stdout)
        self.assertIn("Cannot determine Minecraft state", result.stderr)

    def test_stale_tick_does_not_back_up_new_session(self) -> None:
        (self.root / "mcctl").write_text((ROOT / "mcctl").read_text().removesuffix('main "$@"\n'))
        harness = '''source "$1/mcctl"
backup_control() { :; }
run_local_backup() { echo unexpected; }
run_remote_backup() { echo unexpected; }
command_backup scheduled old-session
'''
        result = subprocess.run(["bash", "-c", harness, "test", str(self.root)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("unexpected", result.stdout)


if __name__ == "__main__":
    unittest.main()
