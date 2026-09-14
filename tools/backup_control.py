#!/usr/bin/env python3
"""Session scheduling and restic/S3 operations. Invoked under mcctl's operation lock.

The scheduler never touches worlds: it dispatches serialized mcctl commands.
S3 inventory uses the standard library and AWS Signature V4 (path-style URLs).
"""
from __future__ import annotations

import argparse
import configparser
import datetime as dt
import hashlib
import hmac
import json
import os
import re
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import xml.etree.ElementTree as ET


class BackupError(Exception):
    pass


def read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        return {}


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        json.dump(value, stream, ensure_ascii=False)
        stream.write("\n")
    temporary.replace(path)


def control_dir(root: Path) -> Path:
    return root / "runtime" / "backup-control"


def compose(root: Path) -> list[str]:
    return ["docker", "compose", "--project-directory", str(root), "-f", str(root / "compose.yaml")]


def session_start(root: Path, local: str, remote: str) -> None:
    directory = control_dir(root)
    state = {"id": uuid.uuid4().hex, "local": local, "s3": remote,
             "active": local == "on" or remote == "on", "next": time.time() + 7200}
    write_json(directory / "session.json", state)
    if state["active"]:
        with (directory / "scheduler.log").open("ab") as log:
            process = subprocess.Popen(
                [sys.executable, str(Path(__file__).resolve()), "--root", str(root), "scheduler", state["id"]],
                stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                start_new_session=True, close_fds=True,
            )
        state["pid"] = process.pid
        write_json(directory / "session.json", state)


def session_flags(root: Path, session_id: str) -> dict:
    state = read_json(control_dir(root) / "session.json")
    if state.get("id") != session_id or not state.get("active"):
        return {}
    return state


def scheduler(root: Path, session_id: str) -> None:
    while state := session_flags(root, session_id):
        delay = state["next"] - time.time()
        if delay > 0:
            time.sleep(min(delay, 5))
            continue
        # mcctl rechecks the session ID AFTER acquiring the same operation lock.
        subprocess.run(["bash", str(root / "mcctl"), "backup", "scheduled", session_id], check=False)
        # The tick updates next even on failure. Never catch up missed ticks in a burst.
        time.sleep(5)


def positive_int(name: str, default: int) -> int:
    try:
        value = int(os.environ.get(name, str(default)))
    except ValueError as exc:
        raise BackupError(f"{name} must be a positive integer.") from exc
    if value <= 0:
        raise BackupError(f"{name} must be a positive integer.")
    return value


def run_container(command: list[str], name: str, label: str, guard=None) -> str:
    # Files avoid pipe deadlocks during lengthy backups or large JSON inventories.
    with tempfile.TemporaryFile(mode="w+") as output:
        process = subprocess.Popen(command, stdout=output, stderr=subprocess.PIPE, text=True)
        try:
            while True:
                try:
                    _, stderr = process.communicate(timeout=5)
                    break
                except subprocess.TimeoutExpired:
                    if guard is not None:
                        guard()
            if process.returncode:
                # Do not echo raw third-party errors, URLs, or credentials.
                raise BackupError(f"{label} failed (exit {process.returncode}); check configuration, access, password and backup locks.")
            output.seek(0)
            return output.read()
        finally:
            if process.poll() is None:
                # Killing the Docker CLI alone leaves a container uploading in the background.
                subprocess.run(["docker", "stop", "-t", "30", name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
                subprocess.run(["docker", "rm", "-f", name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
                process.terminate()
                try:
                    process.communicate(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.communicate()


def rcon(root: Path, command: str) -> None:
    result = subprocess.run(compose(root) + ["exec", "-T", "minecraft", "rcon-cli", command],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    if result.returncode:
        raise BackupError(f"RCON '{command}' failed; verify Minecraft and restore saving with './mcctl rcon save-on'.")


def local_backup(root: Path) -> None:
    token = uuid.uuid4().hex
    name = "wezza-local-" + token
    archive_prefix = "wezza-mc-" + token[:16]
    directory = root / "runtime" / "backups" / "local"
    latest = directory / "latest.tar.zst"
    previous = os.readlink(latest) if latest.is_symlink() else None
    command = compose(root) + ["run", "--rm", "--no-deps", "-T", "--name", name,
                               "-e", f"BACKUP_NAME={archive_prefix}", "backup-local", "now"]
    try:
        try:
            run_container(command, name, "Local backup")
        finally:
            # Also recover saving if the one-shot container was interrupted or failed.
            rcon(root, "save-on")
    except BaseException:
        # Only quarantine archives created by this invocation, never earlier recovery points.
        for archive in directory.glob(f"{archive_prefix}-*.tar.zst"):
            if archive.is_file() and not archive.is_symlink():
                archive.rename(archive.with_name(archive.name + ".failed"))
        if latest.is_symlink() and os.readlink(latest).startswith(archive_prefix + "-"):
            latest.unlink()
            if previous and (directory / previous).is_file():
                latest.symlink_to(previous)
        raise
    print("One-shot local backup completed.")


class S3:
    def __init__(self, root: Path):
        repository = os.environ.get("RESTIC_REPOSITORY", "")
        if not repository.startswith("s3:"):
            raise BackupError("Set RESTIC_REPOSITORY=s3:http(s)://endpoint/bucket/prefix.")
        url = urllib.parse.urlsplit(repository[3:])
        parts = url.path.strip("/").split("/", 1)
        if (url.scheme not in {"http", "https"} or not url.netloc or url.username
                or url.query or url.fragment or len(parts) != 2 or not all(parts)):
            raise BackupError("S3 repository requires an endpoint, bucket and dedicated prefix.")
        self.endpoint = f"{url.scheme}://{url.netloc}"
        self.bucket, self.prefix = (urllib.parse.unquote(part) for part in parts)
        self.prefix = self.prefix.rstrip("/") + "/"
        if any(part in {".", "..", ""} for part in self.prefix.rstrip("/").split("/")):
            raise BackupError("Use a non-empty, dedicated S3 repository prefix.")
        config = configparser.ConfigParser(interpolation=None)
        config.read(root / "secrets" / "aws_credentials")
        try:
            self.access = config["default"]["aws_access_key_id"].strip()
            self.secret = config["default"]["aws_secret_access_key"].strip()
        except KeyError as exc:
            raise BackupError("Missing [default] S3 credentials in secrets/aws_credentials.") from exc
        if not self.access or not self.secret:
            raise BackupError("S3 credentials must not be empty.")
        self.limit = 0
        self.token = config["default"].get("aws_session_token", "").strip()
        self.region = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
        if self.region == "auto":
            self.region = "us-east-1"

    def request(self, method: str, key: str = "", query: dict | None = None, *, service_root: bool = False) -> bytes:
        quote = lambda value: urllib.parse.quote(str(value), safe="-_.~")
        path = "/" if service_root else "/" + quote(self.bucket) + "/" + urllib.parse.quote(key, safe="/-_.~")
        query_string = "&".join(f"{quote(k)}={quote(v)}" for k, v in sorted((query or {}).items()))
        now = dt.datetime.now(dt.timezone.utc)
        date, stamp = now.strftime("%Y%m%d"), now.strftime("%Y%m%dT%H%M%SZ")
        payload_hash = hashlib.sha256(b"").hexdigest()
        headers = {"host": urllib.parse.urlsplit(self.endpoint).netloc,
                   "x-amz-content-sha256": payload_hash, "x-amz-date": stamp}
        if self.token:
            headers["x-amz-security-token"] = self.token
        signed = ";".join(sorted(headers))
        canonical_headers = "".join(f"{k}:{headers[k]}\n" for k in sorted(headers))
        canonical = "\n".join([method, path, query_string, canonical_headers, signed, payload_hash])
        scope = f"{date}/{self.region}/s3/aws4_request"
        message = "\n".join(["AWS4-HMAC-SHA256", stamp, scope, hashlib.sha256(canonical.encode()).hexdigest()])
        signing_key = ("AWS4" + self.secret).encode()
        for component in (date, self.region, "s3", "aws4_request"):
            signing_key = hmac.new(signing_key, component.encode(), hashlib.sha256).digest()
        signature = hmac.new(signing_key, message.encode(), hashlib.sha256).hexdigest()
        headers["Authorization"] = f"AWS4-HMAC-SHA256 Credential={self.access}/{scope}, SignedHeaders={signed}, Signature={signature}"
        request = urllib.request.Request(self.endpoint + path + ("?" + query_string if query_string else ""),
                                         headers=headers, method=method)
        # Credentials must never be forwarded to a redirect or an HTTP proxy.
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, hdrs, newurl):
                return None
        try:
            with urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect()).open(request, timeout=15) as response:
                chunks = []
                started = time.monotonic()
                size = 0
                while chunk := response.read(65536):
                    chunks.append(chunk)
                    size += len(chunk)
                    if self.limit:
                        delay = size / (self.limit * 1024) - (time.monotonic() - started)
                        if delay > 0:
                            time.sleep(delay)
                return b"".join(chunks)
        except urllib.error.HTTPError as exc:
            code = "HTTPError"
            try:
                candidate = ET.fromstring(exc.read(8192)).findtext("{*}Code", "")
                if re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", candidate):
                    code = candidate
            except (ET.ParseError, OSError):
                pass
            raise BackupError(f"S3 {method} failed (HTTP {exc.code}: {code}); check endpoint, bucket and permissions.") from None
        except (OSError, ValueError) as exc:
            raise BackupError(f"S3 {method} failed ({type(exc).__name__}); check endpoint, bucket and permissions.") from None

    def objects(self, prefix: str = "") -> list[tuple[str, int]]:
        objects: list[tuple[str, int]] = []
        token = ""
        seen: set[str] = set()
        while True:
            query = {"list-type": "2", "prefix": prefix, "max-keys": "1000"}
            if token:
                query["continuation-token"] = token
            try:
                document = ET.fromstring(self.request("GET", query=query))
                if document.tag.rsplit("}", 1)[-1] != "ListBucketResult":
                    raise ValueError("not an S3 listing")
                for item in document.findall("{*}Contents"):
                    key, size = item.findtext("{*}Key"), int(item.findtext("{*}Size", "-1"))
                    if key is None or size < 0:
                        raise ValueError("invalid S3 object")
                    objects.append((key, size))
                truncated = document.findtext("{*}IsTruncated")
                if truncated not in {"true", "false"}:
                    raise ValueError("missing pagination state")
                if truncated == "false":
                    return objects
                token = document.findtext("{*}NextContinuationToken", "")
                if not token or token in seen:
                    raise ValueError("invalid continuation token")
                seen.add(token)
            except (ET.ParseError, ValueError) as exc:
                raise BackupError("Invalid S3 inventory; refusing upload or cleanup. Check the S3 API endpoint.") from exc

    def usage(self) -> int:
        # Include other prefixes in the bucket's capacity, but never delete them.
        return sum(size for _, size in self.objects())


def snapshot_time(item: dict) -> dt.datetime:
    value = dt.datetime.fromisoformat(item["time"].replace("Z", "+00:00"))
    if value.tzinfo is None:
        raise BackupError("Snapshot time lacks a timezone; refusing automatic deletion.")
    return value


class Remote:
    def __init__(self, root: Path, online: bool):
        self.root, self.online = root, online
        self.s3 = S3(root)
        self.limit = positive_int("S3_ONLINE_LIMIT_KIB", 5120) if online else 0
        self.s3.limit = self.limit
        os.environ["AWS_DEFAULT_REGION"] = self.s3.region
        self.target = positive_int("S3_TARGET_BYTES", 80_000_000_000)
        self.high = positive_int("S3_HIGH_WATER_BYTES", 90_000_000_000)
        self.capacity = positive_int("S3_CAPACITY_BYTES", 100_000_000_000)
        if not self.target < self.high < self.capacity:
            raise BackupError("Require S3_TARGET_BYTES < S3_HIGH_WATER_BYTES < S3_CAPACITY_BYTES.")
        self.host = os.environ.get("RESTIC_HOSTNAME", "wezza-home-pc")
        self.extra_volumes: list[str] = []
        self.source = "/data"

    def restic(self, *args: str, monitor: bool = False, ceiling: int | None = None) -> str:
        name = "wezza-restic-" + uuid.uuid4().hex
        command = compose(self.root) + ["--profile", "remote", "run", "--rm", "--no-deps", "-T", "--name", name]
        command += ["--user", f"{os.getuid()}:{os.getgid()}"]
        command += self.extra_volumes
        command += ["--entrypoint", "restic", "backup-remote", "-o", "s3.bucket-lookup=path",
                    "--limit-upload", str(self.limit), "--limit-download", str(self.limit)]
        command += list(args)
        def guard() -> None:
            if self.s3.usage() >= (ceiling or self.high):
                raise BackupError("S3 reached its high-water mark; upload stopped. Run 'backup remote' to retry after cleanup.")
        return run_container(command, name, f"restic {args[0]}", guard if monitor else None)

    def snapshots(self) -> list[dict]:
        return json.loads(self.restic("snapshots", "--json", "--host", self.host, "--tag", "wezza-mc"))

    def check(self) -> None:
        usage = self.s3.usage()
        self.snapshots()  # Proves that the existing repository can be decrypted.
        print(f"S3 repository accessible; bucket usage {usage:,} / {self.capacity:,} bytes.")

    @staticmethod
    def protected(snapshots: list[dict]) -> set[str]:
        if not snapshots:
            return set()
        newest = max(snapshots, key=snapshot_time)
        protected = {newest["id"]}
        shutdowns = [item for item in snapshots if "session_end" in item.get("tags", [])]
        if shutdowns:
            protected.add(max(shutdowns, key=snapshot_time)["id"])
        return protected

    def prune(self) -> None:
        # Repack in small batches so the reserved space is not exhausted.
        self.restic("prune", "--max-repack-size", "1G", monitor=True, ceiling=self.capacity - 1_000_000_000)
        self.restic("check")

    def cleanup(self, retention: bool = False) -> None:
        snapshots = self.snapshots()
        protected = self.protected(snapshots)
        if retention and snapshots:
            policy = json.loads(self.restic(
                "forget", "--dry-run", "--json", "--host", self.host, "--tag", "wezza-mc",
                "--group-by", "", "--keep-last", "12", "--keep-daily", "14",
                "--keep-weekly", "8", "--keep-monthly", "12"))
            remove = [item["id"] for group in policy for item in (group.get("remove") or [])
                      if item["id"] not in protected]
            if remove:
                self.restic("forget", *remove)
                self.prune()
                snapshots = self.snapshots()
        usage = self.s3.usage()
        if usage >= self.target:
            # Reclaim unreferenced data left by interrupted uploads before sacrificing snapshots.
            self.prune()
            usage = self.s3.usage()
        for snapshot in sorted(snapshots, key=snapshot_time):
            if usage < self.target:
                break
            if snapshot["id"] in protected:
                continue
            self.restic("forget", snapshot["id"])
            self.prune()
            usage = self.s3.usage()
        if usage >= self.high:
            raise BackupError("S3 capacity budget exhausted; protected snapshots or other bucket data cannot be removed automatically.")

    def rcon(self, command: str) -> None:
        rcon(self.root, command)

    def discard_pending(self) -> None:
        pending = json.loads(self.restic("snapshots", "--json", "--host", self.host, "--tag", "wezza-mc-pending"))
        if pending:
            self.restic("forget", *(item["id"] for item in pending))
            self.prune()

    def backup(self) -> None:
        self.check()
        self.discard_pending()
        self.cleanup()
        token = "operation-" + uuid.uuid4().hex
        try:
            if self.online:
                self.rcon("save-off")
                self.rcon("save-all flush")
            self.restic("backup", self.source, "--host", self.host,
                        "--tag", "wezza-mc-pending", "--tag", token,
                        "--exclude", "*.jar", "--exclude", "cache", "--exclude", "logs",
                        "--exclude", "*.tmp", monitor=True)
        finally:
            if self.online:
                self.rcon("save-on")
        # restic may create an incomplete snapshot with exit code 3. Only a successful
        # backup and restored saving are promoted into the normal retention set.
        pending = json.loads(self.restic("snapshots", "--json", "--host", self.host, "--tag", token))
        if len(pending) != 1:
            raise BackupError("Expected one completed S3 snapshot; refusing to mark this operation successful.")
        self.restic("tag", "--set", "wezza-mc," + ("scheduled" if self.online else "session_end"), pending[0]["id"])
        self.cleanup(retention=True)
        print("S3 backup and retention completed.")

    def initialize(self) -> None:
        # Exercise a unique disposable repository, including object deletion and full restore.
        if self.s3.usage() >= self.high:
            raise BackupError("Not enough capacity to validate and initialize S3.")
        if self.s3.objects(self.s3.prefix):
            self.check()
            return  # Never initialize over existing or unreadable repository data.
        original = os.environ["RESTIC_REPOSITORY"]
        probe_prefix = self.s3.prefix + "validation-" + uuid.uuid4().hex + "/"
        try:
            os.environ["RESTIC_REPOSITORY"] = original.rstrip("/") + "/" + probe_prefix[len(self.s3.prefix):].rstrip("/")
            with tempfile.TemporaryDirectory(prefix="wezza-s3-validation-") as directory:
                source = Path(directory) / "source"
                restored = Path(directory) / "restored"
                source.mkdir()
                restored.mkdir()
                # Override the production /data mount with disposable fixtures for every probe operation.
                self.extra_volumes = ["-v", f"{source}:/data:ro", "-v", f"{restored}:/restore"]
                self.restic("init")
                sample = source / "sample.txt"
                sample.write_bytes(b"wezza-s3-validation\n")
                self.restic("backup", "/data", "--host", self.host, "--tag", "wezza-mc")
                sample.write_bytes(b"wezza-s3-validation-incremental\n")
                self.restic("backup", "/data", "--host", self.host, "--tag", "wezza-mc")
                self.restic("forget", "--keep-last", "1", "--prune")
                self.restic("check", "--read-data")
                self.restic("restore", "latest", "--target", "/restore")
                if (restored / "data" / "sample.txt").read_bytes() != sample.read_bytes():
                    raise BackupError("S3 validation restore does not match its source.")
        finally:
            os.environ["RESTIC_REPOSITORY"] = original
            self.extra_volumes = []
            for key, _ in self.s3.objects(probe_prefix):
                if not key.startswith(probe_prefix):
                    raise BackupError("Unexpected object outside validation prefix; cleanup stopped.")
                self.s3.request("DELETE", key)
        self.restic("init")
        self.check()
        print("S3 read/write, incremental backup, prune and restore verified; repository initialized.")


def record(root: Path, kind: str, success: bool, detail: str) -> None:
    path = control_dir(root) / "results.json"
    results = read_json(path)
    results[kind] = {"success": success, "time": dt.datetime.now(dt.timezone.utc).isoformat(), "detail": detail}
    write_json(path, results)


def enable_remote(root: Path) -> None:
    path = root / ".env"
    content = path.read_text()
    setting = "ENABLE_REMOTE_BACKUP=true"
    if re.search(r"^ENABLE_REMOTE_BACKUP=.*$", content, re.MULTILINE):
        content = re.sub(r"^ENABLE_REMOTE_BACKUP=.*$", setting, content, flags=re.MULTILINE)
    else:
        content = content.rstrip("\n") + "\n" + setting + "\n"
    with tempfile.NamedTemporaryFile(mode="w", dir=root, delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(content)
    temporary.chmod(0o600)
    temporary.replace(path)


def status(root: Path) -> None:
    state = read_json(control_dir(root) / "session.json")
    active = state.get("active", False)
    if active:
        try:
            pid = state.get("pid", 0)
            if pid <= 0:
                raise ProcessLookupError
            os.kill(pid, 0)
            command = Path(f"/proc/{pid}/cmdline").read_bytes()
            active = b"backup_control.py" in command and state["id"].encode() in command
        except OSError:
            active = False
    print(f"两小时备份：本机 {state.get('local', 'off')} / S3 {state.get('s3', 'on')} · 调度{'运行中' if active else '未运行'}")
    for kind, result in read_json(control_dir(root) / "results.json").items():
        print(f"{kind}: {'成功' if result['success'] else '失败'} · {result['time']} · {result['detail']}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("action", choices=["session-start", "session-stop", "session-flags", "session-next",
                                           "scheduler", "local", "remote", "remote-check", "remote-init", "status", "record"])
    parser.add_argument("values", nargs="*")
    args = parser.parse_args()
    root = args.root.resolve()
    action = args.action
    try:
        if action == "session-start":
            session_start(root, *args.values)
        elif action == "session-stop":
            path = control_dir(root) / "session.json"
            state = read_json(path)
            state["active"] = False
            write_json(path, state)
        elif action == "session-flags":
            state = session_flags(root, args.values[0])
            if state:
                print(state["local"], state["s3"])
        elif action == "session-next":
            state = session_flags(root, args.values[0])
            if state:
                state["next"] = time.time() + 7200
                write_json(control_dir(root) / "session.json", state)
        elif action == "scheduler":
            scheduler(root, args.values[0])
        elif action == "status":
            status(root)
        elif action == "local":
            local_backup(root)
            record(root, "local", True, "One-shot local backup completed")
        elif action == "record":
            record(root, args.values[0], args.values[1] == "0", args.values[2])
        else:
            remote = Remote(root, online=bool(args.values and args.values[0] == "online"))
            if action == "remote-check":
                remote.check()
            elif action == "remote-init":
                remote.initialize()
                enable_remote(root)
            else:
                remote.backup()
            record(root, "S3" if action == "remote" else "S3 readiness", True, action + " completed")
        return 0
    except (BackupError, OSError, ValueError, KeyError, KeyboardInterrupt) as exc:
        message = str(exc) if isinstance(exc, BackupError) else f"{type(exc).__name__}; inspect configuration and retry."
        if action == "local":
            record(root, "local", False, message)
        if action.startswith("remote"):
            record(root, "S3" if action == "remote" else "S3 readiness", False, message)
        print(f"Backup error: {message}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    def interrupted(*_):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, interrupted)
    sys.exit(main())
