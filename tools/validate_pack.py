#!/usr/bin/env python3
"""Validate the Packwiz source without contacting third-party services."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import tomllib
from urllib.parse import urlparse


VALID_SIDES = {"client", "server", "both"}
VALID_HASHES = {"sha1": 40, "sha256": 64, "sha512": 128, "md5": 32}


def load_toml(path: Path) -> dict:
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ValueError(f"{path}: cannot read TOML: {exc}") from exc


def digest(path: Path, algorithm: str) -> str:
    hasher = hashlib.new(algorithm)
    hasher.update(path.read_bytes())
    return hasher.hexdigest()


def validate(pack_dir: Path) -> tuple[list[dict], list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    result: list[dict] = []

    pack_file = pack_dir / "pack.toml"
    index_file = pack_dir / "index.toml"
    if not pack_file.is_file():
        return [], [f"missing {pack_file}"], []
    if not index_file.is_file():
        return [], [f"missing {index_file}; run './mcctl mod check'"], []

    try:
        pack = load_toml(pack_file)
        index = load_toml(index_file)
    except ValueError as exc:
        return [], [str(exc)], []

    versions = pack.get("versions", {})
    if versions.get("minecraft") != "26.1.2":
        errors.append("pack.toml must pin Minecraft 26.1.2")
    if versions.get("fabric") != "0.19.3":
        errors.append("pack.toml must pin Fabric Loader 0.19.3")

    index_cfg = pack.get("index", {})
    index_hash_format = index_cfg.get("hash-format")
    index_hash = index_cfg.get("hash")
    if index_hash_format not in VALID_HASHES:
        errors.append("pack.toml has an unsupported index hash format")
    elif digest(index_file, index_hash_format) != index_hash:
        errors.append("pack.toml index hash is stale; run Packwiz refresh")

    indexed = {entry.get("file"): entry for entry in index.get("files", [])}
    names: set[str] = set()
    filenames: set[str] = set()

    for mod_path in sorted((pack_dir / "mods").glob("*.pw.toml")):
        rel = mod_path.relative_to(pack_dir).as_posix()
        slug = mod_path.name.removesuffix(".pw.toml")
        try:
            mod = load_toml(mod_path)
        except ValueError as exc:
            errors.append(str(exc))
            continue

        name = str(mod.get("name", "")).strip()
        filename = str(mod.get("filename", "")).strip()
        side = mod.get("side")
        download = mod.get("download", {})
        update = mod.get("update", {})

        if not name:
            errors.append(f"{rel}: missing name")
        elif name.casefold() in names:
            errors.append(f"{rel}: duplicate mod name {name!r}")
        names.add(name.casefold())

        if not filename.endswith(".jar"):
            errors.append(f"{rel}: filename must end with .jar")
        elif filename.casefold() in filenames:
            errors.append(f"{rel}: duplicate destination filename {filename!r}")
        filenames.add(filename.casefold())

        if re.search(r"(?:^|[-+._])(alpha|beta|snapshot)(?:[-+._]|$)", filename.casefold()):
            errors.append(
                f"{rel}: pre-release artifact detected; stable releases are required by default"
            )

        if side not in VALID_SIDES:
            errors.append(f"{rel}: side must be client, server, or both")

        mode = download.get("mode", "url")
        hash_format = download.get("hash-format")
        hash_value = str(download.get("hash", "")).lower()
        if hash_format not in VALID_HASHES:
            errors.append(f"{rel}: unsupported or missing download hash format")
        elif len(hash_value) != VALID_HASHES[hash_format] or any(
            char not in "0123456789abcdef" for char in hash_value
        ):
            errors.append(f"{rel}: invalid {hash_format} download hash")

        source = "external"
        if "modrinth" in update:
            source = "modrinth"
            if not update["modrinth"].get("mod-id") or not update["modrinth"].get("version"):
                errors.append(f"{rel}: incomplete Modrinth update metadata")
        elif "curseforge" in update or mode == "metadata:curseforge":
            source = "curseforge"
        elif mode == "url":
            url = str(download.get("url", ""))
            parsed = urlparse(url)
            if parsed.scheme != "https" or not parsed.netloc:
                errors.append(f"{rel}: external downloads must use an HTTPS URL")
            if parsed.netloc not in {
                "github.com",
                "objects.githubusercontent.com",
                "raw.githubusercontent.com",
                "gitlab.com",
                "cdn.modrinth.com",
            }:
                warnings.append(
                    f"{rel}: verify redistribution permission for external host {parsed.netloc}"
                )

        entry = indexed.get(rel)
        if not entry:
            errors.append(f"{rel}: absent from index.toml")
        else:
            if not entry.get("metafile"):
                errors.append(f"{rel}: index entry must set metafile = true")
            expected_hash = entry.get("hash")
            index_algorithm = index.get("hash-format")
            if index_algorithm in VALID_HASHES and digest(mod_path, index_algorithm) != expected_hash:
                errors.append(f"{rel}: stale hash in index.toml")

        result.append(
            {
                "slug": slug,
                "name": name,
                "filename": filename,
                "side": side,
                "source": source,
                "metadata": rel,
                "download_url": download.get("url"),
                "project_url": (
                    f"https://modrinth.com/mod/{update['modrinth'].get('mod-id')}"
                    if source == "modrinth" and update["modrinth"].get("mod-id")
                    else None
                ),
                "version_url": (
                    "https://modrinth.com/mod/"
                    f"{update['modrinth'].get('mod-id')}/version/{update['modrinth'].get('version')}"
                    if source == "modrinth"
                    and update["modrinth"].get("mod-id")
                    and update["modrinth"].get("version")
                    else None
                ),
            }
        )

    known_paths = {path.relative_to(pack_dir).as_posix() for path in (pack_dir / "mods").glob("*.pw.toml")}
    extra_metafiles = {
        rel for rel, entry in indexed.items() if entry.get("metafile") and rel not in known_paths
    }
    for rel in sorted(extra_metafiles):
        errors.append(f"index.toml references missing/unexpected metafile {rel}")

    return result, errors, warnings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("pack_dir", nargs="?", default="pack", type=Path)
    parser.add_argument("--json-output", type=Path)
    args = parser.parse_args()

    mods, errors, warnings = validate(args.pack_dir.resolve())
    if mods:
        headers = ("SLUG", "SIDE", "SOURCE", "MOD")
        rows = [
            (
                str(mod["slug"]),
                str(mod["side"] or ""),
                str(mod["source"]),
                str(mod["name"]),
            )
            for mod in mods
        ]
        widths = [
            max(len(header), *(len(row[index]) for row in rows))
            for index, header in enumerate(headers)
        ]
        print(
            "  ".join(
                f"{header:<{widths[index]}}" for index, header in enumerate(headers)
            ).rstrip()
        )
        for row in rows:
            print(
                "  ".join(
                    f"{value:<{widths[index]}}" for index, value in enumerate(row)
                ).rstrip()
            )
        counts = {side: sum(mod["side"] == side for mod in mods) for side in sorted(VALID_SIDES)}
        print(
            f"\nImpact: {counts['server']} server-only, "
            f"{counts['client']} client-only, {counts['both']} required on both"
        )

    for warning in warnings:
        print(f"warning: {warning}", file=sys.stderr)
    for error in errors:
        print(f"error: {error}", file=sys.stderr)

    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(
            json.dumps({"mods": mods}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    if errors:
        return 1
    print("\nPack validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
