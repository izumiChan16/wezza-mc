#!/usr/bin/env python3
"""Prepare release metadata and validate standard Modrinth .mrpack exports."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tomllib
from urllib.parse import urlparse
import zipfile


VERSION_PATTERN = re.compile(r"^(?P<minecraft>.+)-r(?P<revision>[1-9][0-9]*)$")


def load_toml(path: Path) -> dict:
    return tomllib.loads(path.read_text(encoding="utf-8"))


def load_toml_text(text: str) -> dict:
    return tomllib.loads(text)


def load_mods(pack_dir: Path) -> dict[str, dict]:
    mods: dict[str, dict] = {}
    for path in sorted((pack_dir / "mods").glob("*.pw.toml")):
        mods[path.relative_to(pack_dir).as_posix()] = load_toml(path)
    return mods


def mod_source(mod: dict) -> str:
    update = mod.get("update", {})
    mode = mod.get("download", {}).get("mode", "url")
    if "modrinth" in update:
        return "modrinth"
    if "curseforge" in update or mode == "metadata:curseforge":
        return "curseforge"
    return "external"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def approval_map(path: Path) -> dict[str, dict]:
    if not path.is_file():
        return {}
    data = load_toml(path)
    if data.get("schema") != 1:
        raise ValueError(f"{path}: schema must be 1")
    files = data.get("files", {})
    if not isinstance(files, dict):
        raise ValueError(f"{path}: [files] must be a table")
    return files


def check_redistribution(pack_dir: Path, approvals_path: Path) -> list[str]:
    errors: list[str] = []
    mods = load_mods(pack_dir)
    try:
        approvals = approval_map(approvals_path)
    except (OSError, tomllib.TOMLDecodeError, ValueError) as exc:
        return [str(exc)]

    for rel, mod in mods.items():
        source = mod_source(mod)
        if source == "modrinth":
            continue
        approval = approvals.get(rel)
        if not isinstance(approval, dict):
            errors.append(
                f"{rel}: {source} files need an explicit redistribution approval"
            )
            continue
        if approval.get("approved") is not True:
            errors.append(f"{rel}: redistribution approval must set approved = true")
        expected_hash = approval.get("metadata-sha256")
        actual_hash = sha256(pack_dir / rel)
        if expected_hash != actual_hash:
            errors.append(
                f"{rel}: approval metadata-sha256 is missing or stale; expected {actual_hash}"
            )
        license_url = str(approval.get("license-url", ""))
        parsed = urlparse(license_url)
        if parsed.scheme != "https" or not parsed.netloc:
            errors.append(f"{rel}: approval needs an HTTPS license-url")

    for rel in sorted(set(approvals) - set(mods)):
        errors.append(f"{approvals_path}: approval references missing metadata {rel}")
    return errors


def git_text(repo_root: Path, revision: str, rel: str) -> str | None:
    result = subprocess.run(
        ["git", "-C", str(repo_root), "show", f"{revision}:{rel}"],
        check=False,
        capture_output=True,
        text=True,
    )
    return result.stdout if result.returncode == 0 else None


def git_old_mods(repo_root: Path, revision: str) -> dict[str, dict]:
    result = subprocess.run(
        [
            "git",
            "-C",
            str(repo_root),
            "ls-tree",
            "-r",
            "--name-only",
            revision,
            "--",
            "pack/mods",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    mods: dict[str, dict] = {}
    for repo_rel in result.stdout.splitlines():
        if not repo_rel.endswith(".pw.toml"):
            continue
        text = git_text(repo_root, revision, repo_rel)
        if text is not None:
            mods[repo_rel.removeprefix("pack/")] = load_toml_text(text)
    return mods


def mod_public_data(mod: dict | None) -> dict:
    if mod is None:
        return {}
    update = mod.get("update", {})
    modrinth = update.get("modrinth", {})
    project_id = modrinth.get("mod-id")
    version_id = modrinth.get("version")
    download = mod.get("download", {})
    result = {
        "name": mod.get("name", ""),
        "filename": mod.get("filename", ""),
        "side": mod.get("side", "both"),
        "source": mod_source(mod),
        "download_url": download.get("url"),
        "hash_format": download.get("hash-format"),
        "hash": download.get("hash"),
        "project_url": None,
        "version_url": None,
    }
    if project_id:
        result["project_url"] = f"https://modrinth.com/mod/{project_id}"
        if version_id:
            result["version_url"] = (
                f"https://modrinth.com/mod/{project_id}/version/{version_id}"
            )
    return result


def meaningful_mod_value(mod: dict) -> tuple:
    download = mod.get("download", {})
    return (
        mod.get("name"),
        mod.get("filename"),
        mod.get("side"),
        download.get("mode"),
        download.get("url"),
        download.get("hash-format"),
        download.get("hash"),
        json.dumps(mod.get("update", {}), sort_keys=True),
    )


def build_changes(old_mods: dict[str, dict], new_mods: dict[str, dict]) -> list[dict]:
    changes: list[dict] = []
    for rel in sorted(set(old_mods) | set(new_mods)):
        old = old_mods.get(rel)
        new = new_mods.get(rel)
        if old is not None and new is not None and meaningful_mod_value(old) == meaningful_mod_value(new):
            continue
        if old is None:
            action = "added"
        elif new is None:
            action = "removed"
        elif old.get("filename") != new.get("filename") or old.get("download") != new.get("download"):
            action = "updated"
        else:
            action = "changed"
        old_data = mod_public_data(old)
        new_data = mod_public_data(new)
        old_on_client = old is not None and old_data.get("side") != "server"
        new_on_client = new is not None and new_data.get("side") != "server"
        player_operation: str | None = None
        if not old_on_client and new_on_client:
            player_operation = "added"
        elif old_on_client and not new_on_client:
            player_operation = "removed"
        elif old_on_client and new_on_client:
            old_download = old_data.get("download_url")
            new_download = new_data.get("download_url")
            if old_data.get("filename") != new_data.get("filename") or old_download != new_download:
                player_operation = "updated"
        effective_side = new_data.get("side") or old_data.get("side") or "both"
        changes.append(
            {
                "action": action,
                "player_operation": player_operation,
                "metadata": rel,
                "name": new_data.get("name") or old_data.get("name"),
                "side": effective_side,
                "player_action": player_operation is not None,
                "old": old_data or None,
                "new": new_data or None,
            }
        )
    return changes


def validate_release(pack_dir: Path, release_path: Path) -> list[str]:
    errors: list[str] = []
    pack = load_toml(pack_dir / "pack.toml")
    try:
        release = json.loads(release_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"{release_path}: cannot read release JSON: {exc}"]

    if release.get("schema") != 1:
        errors.append("release metadata schema must be 1")
    if release.get("pack_version") != pack.get("version"):
        errors.append("release pack_version does not match pack.toml")
    versions = pack.get("versions", {})
    if release.get("minecraft") != versions.get("minecraft"):
        errors.append("release Minecraft version does not match pack.toml")
    if release.get("fabric_loader") != versions.get("fabric"):
        errors.append("release Fabric Loader version does not match pack.toml")
    release_type = release.get("release_type")
    if release_type not in {"small", "full"}:
        errors.append("release_type must be small or full")
    if release.get("requires_reimport") is not (release_type == "full"):
        errors.append("requires_reimport does not match release_type")
    if not isinstance(release.get("changes"), list):
        errors.append("release changes must be a list")
    return errors


def replace_pack_version(pack_file: Path, version: str) -> None:
    text = pack_file.read_text(encoding="utf-8")
    updated, count = re.subn(
        r'(?m)^version = "[^"]+"$',
        f'version = "{version}"',
        text,
        count=1,
    )
    if count != 1:
        raise ValueError(f"{pack_file}: expected exactly one top-level version field")
    pack_file.write_text(updated, encoding="utf-8")


def prepare_release(
    pack_dir: Path,
    repo_root: Path,
    release_type: str,
    output: Path,
    revision: str,
) -> dict:
    current = load_toml(pack_dir / "pack.toml")
    minecraft = str(current.get("versions", {}).get("minecraft", ""))
    fabric = str(current.get("versions", {}).get("fabric", ""))
    old_pack_text = git_text(repo_root, revision, "pack/pack.toml")
    if old_pack_text is None:
        raise ValueError(f"cannot read pack/pack.toml from git revision {revision}")
    old_pack = load_toml_text(old_pack_text)
    old_minecraft = str(old_pack.get("versions", {}).get("minecraft", ""))
    old_fabric = str(old_pack.get("versions", {}).get("fabric", ""))
    old_version = str(old_pack.get("version", ""))
    match = VERSION_PATTERN.fullmatch(old_version)
    if match and match.group("minecraft") == minecraft:
        next_revision = int(match.group("revision")) + 1
    else:
        next_revision = 1
    version = f"{minecraft}-r{next_revision}"

    old_mods = git_old_mods(repo_root, revision)
    new_mods = load_mods(pack_dir)
    changes = build_changes(old_mods, new_mods)
    loader_changed = old_fabric != fabric
    minecraft_changed = old_minecraft != minecraft
    if not changes and not loader_changed and not minecraft_changed:
        raise ValueError("no mod, Minecraft, or Fabric changes to publish")
    if release_type == "small" and (minecraft_changed or loader_changed):
        raise ValueError("Minecraft or Fabric changes require a full release")

    replace_pack_version(pack_dir / "pack.toml", version)
    payload = {
        "schema": 1,
        "pack_version": version,
        "previous_pack_version": old_version,
        "minecraft": minecraft,
        "fabric_loader": fabric,
        "release_type": release_type,
        "requires_reimport": release_type == "full",
        "published_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "changes": changes,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def verify_mrpack(pack_dir: Path, mrpack: Path) -> list[str]:
    errors: list[str] = []
    pack = load_toml(pack_dir / "pack.toml")
    mods = load_mods(pack_dir)
    with zipfile.ZipFile(mrpack) as archive:
        try:
            manifest = json.loads(archive.read("modrinth.index.json"))
        except KeyError:
            return ["mrpack is missing modrinth.index.json"]
        if manifest.get("formatVersion") != 1:
            errors.append("mrpack formatVersion must be 1")
        if manifest.get("game") != "minecraft":
            errors.append("mrpack game must be minecraft")
        dependencies = manifest.get("dependencies", {})
        if dependencies.get("minecraft") != pack.get("versions", {}).get("minecraft"):
            errors.append("mrpack Minecraft dependency does not match pack.toml")
        if dependencies.get("fabric-loader") != pack.get("versions", {}).get("fabric"):
            errors.append("mrpack Fabric Loader dependency does not match pack.toml")
        if manifest.get("versionId") != pack.get("version"):
            errors.append("mrpack versionId does not match pack.toml version")

        manifest_files = manifest.get("files", [])
        entries = {entry.get("path"): entry for entry in manifest_files}
        if len(entries) != len(manifest_files):
            errors.append("mrpack contains duplicate or missing file paths")
        archive_names = set(archive.namelist())
        expected_paths: set[str] = set()
        server_paths: set[str] = set()
        for mod in mods.values():
            path = f"mods/{mod.get('filename', '')}"
            if mod.get("side") == "server":
                server_paths.add(path)
                entry = entries.get(path)
                if entry and entry.get("env", {}).get("client") != "unsupported":
                    errors.append(f"server-only file lacks client=unsupported in mrpack: {path}")
                if f"overrides/{path}" in archive_names:
                    errors.append(f"server-only file was bundled into client overrides: {path}")
                continue
            expected_paths.add(path)
            override_path = f"overrides/{path}"
            if path not in entries and override_path not in archive_names:
                errors.append(f"client-required file is absent from mrpack: {path}")
            if path in entries and override_path in archive_names:
                errors.append(f"client-required file is duplicated in manifest and overrides: {path}")
            entry = entries.get(path)
            if entry and entry.get("env", {}).get("client") == "unsupported":
                errors.append(f"client-required file is marked unsupported: {path}")
            download = mod.get("download", {})
            expected_url = download.get("url")
            if entry and expected_url and expected_url not in entry.get("downloads", []):
                errors.append(f"mrpack download URL differs for {path}")
            if entry:
                hash_format = download.get("hash-format")
                hash_value = download.get("hash")
                if hash_format not in entry.get("hashes", {}):
                    errors.append(f"mrpack is missing the {hash_format} hash for {path}")
                elif entry["hashes"][hash_format] != hash_value:
                    errors.append(f"mrpack hash differs for {path}")
            elif override_path in archive_names:
                hash_format = download.get("hash-format")
                hash_value = download.get("hash")
                if hash_format and hash_value:
                    bundled_hash = hashlib.new(hash_format, archive.read(override_path)).hexdigest()
                    if bundled_hash != hash_value:
                        errors.append(f"bundled override hash differs for {path}")

        unexpected = {
            path for path in entries if path and path.startswith("mods/")
        } - expected_paths - server_paths
        for path in sorted(unexpected):
            errors.append(f"unexpected mod file in mrpack: {path}")
        override_mods = {
            name.removeprefix("overrides/")
            for name in archive_names
            if name.startswith("overrides/mods/") and not name.endswith("/")
        }
        for path in sorted(override_mods - expected_paths):
            errors.append(f"unexpected bundled mod in mrpack: {path}")
    return errors


def fail_or_print(errors: list[str], success: str) -> int:
    if errors:
        for error in errors:
            print(f"error: {error}", file=sys.stderr)
        return 1
    print(success)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    safety = subparsers.add_parser("safety")
    safety.add_argument("--pack-dir", type=Path, default=Path("pack"))
    safety.add_argument("--approvals", type=Path, default=Path("pack/redistribution.toml"))

    prepare = subparsers.add_parser("prepare")
    prepare.add_argument("--pack-dir", type=Path, required=True)
    prepare.add_argument("--repo-root", type=Path, default=Path("."))
    prepare.add_argument("--release-type", choices=("small", "full"), required=True)
    prepare.add_argument("--output", type=Path, required=True)
    prepare.add_argument("--revision", default="HEAD")

    verify = subparsers.add_parser("verify")
    verify.add_argument("--pack-dir", type=Path, default=Path("pack"))
    verify.add_argument("--mrpack", type=Path, required=True)

    release_check = subparsers.add_parser("release-check")
    release_check.add_argument("--pack-dir", type=Path, default=Path("pack"))
    release_check.add_argument("--release", type=Path, default=Path("site/release.json"))

    version = subparsers.add_parser("version")
    version.add_argument("--pack-dir", type=Path, default=Path("pack"))

    args = parser.parse_args()
    try:
        if args.command == "safety":
            errors = check_redistribution(args.pack_dir.resolve(), args.approvals.resolve())
            return fail_or_print(errors, "MRPACK redistribution safety passed.")
        if args.command == "prepare":
            payload = prepare_release(
                args.pack_dir.resolve(),
                args.repo_root.resolve(),
                args.release_type,
                args.output.resolve(),
                args.revision,
            )
            print(
                f"Prepared {payload['pack_version']} ({payload['release_type']}) "
                f"with {len(payload['changes'])} change(s)."
            )
            return 0
        if args.command == "verify":
            errors = verify_mrpack(args.pack_dir.resolve(), args.mrpack.resolve())
            return fail_or_print(errors, "MRPACK verification passed.")
        if args.command == "release-check":
            errors = validate_release(args.pack_dir.resolve(), args.release.resolve())
            return fail_or_print(errors, "Release metadata validation passed.")
        if args.command == "version":
            print(load_toml(args.pack_dir.resolve() / "pack.toml")["version"])
            return 0
    except (OSError, ValueError, tomllib.TOMLDecodeError, subprocess.CalledProcessError, zipfile.BadZipFile) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
