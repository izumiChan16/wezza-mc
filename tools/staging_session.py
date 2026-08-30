#!/usr/bin/env python3
"""Track and safely clean isolated mcctl staging sessions."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile


PACK_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
BACKUP_NAME_RE = re.compile(r"^[^/|\x00\r\n]+\.(?:tar\.zst|tgz|tar\.gz)$")
SESSION_SCHEMA = 1


class SessionError(ValueError):
    """A staging session cannot be read or changed safely."""


def paths_for(root: Path) -> tuple[Path, Path]:
    root = root.resolve()
    runtime = root / "runtime"
    staging = runtime / "staging"
    if runtime.is_symlink() or staging.is_symlink():
        raise SessionError("Refusing to use symlinked runtime or staging directories.")
    return staging, staging / "SESSION"


def validate_backup_id(backup_id: str) -> tuple[str, str]:
    try:
        scope, name = backup_id.split("/", 1)
    except ValueError as exc:
        raise SessionError("Backup ID must be local/<name> or offline/<name>.") from exc
    if scope not in {"local", "offline"} or not BACKUP_NAME_RE.fullmatch(name):
        raise SessionError(f"Unsafe staging backup ID: {backup_id}")
    return scope, name


def backup_path(root: Path, backup_id: str) -> Path:
    scope, name = validate_backup_id(backup_id)
    root = root.resolve()
    runtime = root / "runtime"
    backups = runtime / "backups"
    directory = backups / ("local" if scope == "local" else "offline")
    if runtime.is_symlink() or backups.is_symlink() or directory.is_symlink():
        raise SessionError("Refusing to use symlinked backup directories.")
    return directory / name


def validate_session(data: object) -> dict[str, object]:
    if not isinstance(data, dict) or data.get("schema") != SESSION_SCHEMA:
        raise SessionError("Unsupported or invalid staging session schema.")
    pack_sha = data.get("pack_sha256")
    if not isinstance(pack_sha, str) or not PACK_SHA_RE.fullmatch(pack_sha):
        raise SessionError("The staging session contains an invalid pack hash.")
    backup = data.get("backup")
    if not isinstance(backup, dict) or backup.get("status") not in {
        "tracked",
        "untracked",
        "none",
    }:
        raise SessionError("The staging session contains invalid backup metadata.")
    backup_id = backup.get("id", "")
    if not isinstance(backup_id, str):
        raise SessionError("The staging backup ID is invalid.")
    if backup_id:
        validate_backup_id(backup_id)
    if backup["status"] == "tracked":
        if not backup_id:
            raise SessionError("The tracked staging backup ID is missing.")
        for field in ("inode", "size", "mtime_ns"):
            if not isinstance(backup.get(field), int) or int(backup[field]) < 0:
                raise SessionError(f"The staging backup identity is missing {field}.")
    return data


def load_session(root: Path) -> dict[str, object] | None:
    _staging, session_file = paths_for(root)
    if not session_file.exists():
        return None
    if session_file.is_symlink() or not session_file.is_file():
        raise SessionError(f"Refusing unsafe staging session file: {session_file}")
    try:
        data = json.loads(session_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SessionError(f"Cannot read staging session: {exc}") from exc
    return validate_session(data)


def write_session(root: Path, data: dict[str, object]) -> None:
    staging, session_file = paths_for(root)
    staging.mkdir(parents=True, exist_ok=True)
    validate_session(data)
    fd, temporary_name = tempfile.mkstemp(prefix=".SESSION.", dir=staging)
    temporary = Path(temporary_name)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=True, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, session_file)
    except Exception:
        try:
            temporary.unlink(missing_ok=True)
        finally:
            raise


def create_session(
    root: Path, pack_sha: str, backup_status: str, backup_id: str
) -> None:
    if not PACK_SHA_RE.fullmatch(pack_sha):
        raise SessionError("Pack hash must be a lowercase SHA-256 value.")
    if load_session(root) is not None:
        raise SessionError("A staging session already exists.")
    backup: dict[str, object] = {"status": backup_status}
    if backup_id:
        validate_backup_id(backup_id)
        backup["id"] = backup_id
    if backup_status == "tracked":
        if not backup_id:
            raise SessionError("A tracked staging backup requires an ID.")
        archive = backup_path(root, backup_id)
        if archive.is_symlink() or not archive.is_file():
            raise SessionError(f"Tracked staging backup does not exist: {backup_id}")
        stat_result = archive.stat(follow_symlinks=False)
        backup.update(
            inode=stat_result.st_ino,
            size=stat_result.st_size,
            mtime_ns=stat_result.st_mtime_ns,
        )
    elif backup_status == "none" and backup_id:
        raise SessionError("A no-backup session cannot contain a backup ID.")
    write_session(
        root,
        {
            "schema": SESSION_SCHEMA,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "pack_sha256": pack_sha,
            "backup": backup,
        },
    )


def inspect_session(root: Path) -> None:
    data = load_session(root)
    if data is None:
        print("none||||")
        return
    backup = data["backup"]
    assert isinstance(backup, dict)
    print(
        "|".join(
            (
                "active",
                str(data["pack_sha256"]),
                str(backup["status"]),
                str(backup.get("id", "")),
                str(data.get("started_at", "")),
            )
        )
    )


def update_pack(root: Path, pack_sha: str) -> None:
    if not PACK_SHA_RE.fullmatch(pack_sha):
        raise SessionError("Pack hash must be a lowercase SHA-256 value.")
    data = load_session(root)
    if data is None:
        raise SessionError("There is no staging session to update.")
    data["pack_sha256"] = pack_sha
    write_session(root, data)


def staging_data_paths(root: Path) -> list[Path]:
    staging, _session_file = paths_for(root)
    if not staging.exists():
        return []
    paths: list[Path] = []
    current = staging / "data"
    if current.exists() or current.is_symlink():
        paths.append(current)
    for item in staging.iterdir():
        if item.name.startswith("data.previous."):
            paths.append(item)
    return paths


def path_size(path: Path) -> int:
    if path.is_symlink():
        return 0
    if path.is_file():
        try:
            return path.stat(follow_symlinks=False).st_size
        except OSError:
            return 0
    total = 0
    if path.is_dir():
        for directory, dirnames, filenames in os.walk(path, followlinks=False):
            directory_path = Path(directory)
            dirnames[:] = [
                name for name in dirnames if not (directory_path / name).is_symlink()
            ]
            for name in filenames:
                item = directory_path / name
                try:
                    if not item.is_symlink() and item.is_file():
                        total += item.stat(follow_symlinks=False).st_size
                except OSError:
                    continue
    return total


def show_usage(root: Path) -> None:
    paths = staging_data_paths(root)
    print(f"{len(paths)}|{sum(path_size(path) for path in paths)}")


def cleanup_data(root: Path) -> None:
    for path in staging_data_paths(root):
        if path.is_symlink() or path.is_file():
            path.unlink()
        elif path.is_dir():
            shutil.rmtree(path)


def delete_session_backup(root: Path) -> int:
    data = load_session(root)
    if data is None:
        raise SessionError("There is no staging session.")
    backup = data["backup"]
    assert isinstance(backup, dict)
    status = str(backup["status"])
    if status == "none":
        print("No staging-specific backup was created.")
        return 0
    backup_id = str(backup.get("id", ""))
    if status != "tracked" or not backup_id:
        print("The staging backup was not uniquely tracked and was kept.")
        return 2
    archive = backup_path(root, backup_id)
    if archive.is_symlink() or not archive.is_file():
        print(f"The tracked staging backup is missing or unsafe and was kept: {backup_id}")
        return 2
    stat_result = archive.stat(follow_symlinks=False)
    identity = (stat_result.st_ino, stat_result.st_size, stat_result.st_mtime_ns)
    expected = (backup["inode"], backup["size"], backup["mtime_ns"])
    if identity != expected:
        print(f"The tracked staging backup changed and was kept: {backup_id}")
        return 2
    archive.unlink()
    print(f"Deleted the staging-specific backup: {backup_id}")
    return 0


def clear_session(root: Path) -> None:
    _staging, session_file = paths_for(root)
    if session_file.is_symlink():
        raise SessionError(f"Refusing unsafe staging session file: {session_file}")
    session_file.unlink(missing_ok=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("inspect", "usage", "cleanup-data", "delete-backup", "clear"):
        command = subparsers.add_parser(name)
        command.add_argument("--root", type=Path, required=True)
    record = subparsers.add_parser("record")
    record.add_argument("--root", type=Path, required=True)
    record.add_argument("--pack-sha", required=True)
    record.add_argument(
        "--backup-status", choices=("tracked", "untracked", "none"), required=True
    )
    record.add_argument("--backup-id", default="")
    update = subparsers.add_parser("update-pack")
    update.add_argument("--root", type=Path, required=True)
    update.add_argument("--pack-sha", required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.command == "record":
            create_session(args.root, args.pack_sha, args.backup_status, args.backup_id)
        elif args.command == "inspect":
            inspect_session(args.root)
        elif args.command == "update-pack":
            update_pack(args.root, args.pack_sha)
        elif args.command == "usage":
            show_usage(args.root)
        elif args.command == "cleanup-data":
            cleanup_data(args.root)
        elif args.command == "delete-backup":
            return delete_session_backup(args.root)
        elif args.command == "clear":
            clear_session(args.root)
    except SessionError as exc:
        parser_error = f"error: {exc}"
        print(parser_error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
