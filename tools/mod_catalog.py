#!/usr/bin/env python3
"""Show online mod compatibility and official project details."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
from pathlib import Path
import sys
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

try:
    from .validate_pack import load_toml, validate
except ImportError:
    from validate_pack import load_toml, validate


DEFAULT_API_BASE = "https://api.modrinth.com/v2"
USER_AGENT = "wezza-mc/mcctl (https://github.com/izumiChan16/wezza_mc)"
UNKNOWN = "unknown"


class CatalogError(RuntimeError):
    """Raised when official project data cannot be retrieved or understood."""


def api_base() -> str:
    return os.environ.get("MCCTL_MODRINTH_API_BASE", DEFAULT_API_BASE).rstrip("/")


def fetch_json(path: str) -> object:
    request = Request(
        f"{api_base()}/{path.lstrip('/')}",
        headers={"Accept": "application/json", "User-Agent": USER_AGENT},
    )
    try:
        with urlopen(request, timeout=8) as response:
            return json.load(response)
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        raise CatalogError(str(exc)) from exc


def minecraft_release_dates(
    fetcher: Callable[[str], object] = fetch_json,
) -> dict[str, str]:
    payload = fetcher("tag/game_version")
    if not isinstance(payload, list):
        raise CatalogError("Modrinth returned an invalid game-version list")
    releases: dict[str, str] = {}
    for item in payload:
        if not isinstance(item, dict) or item.get("version_type") != "release":
            continue
        version = item.get("version")
        date = item.get("date")
        if isinstance(version, str) and isinstance(date, str):
            releases[version] = date
    if not releases:
        raise CatalogError("Modrinth returned no official Minecraft releases")
    return releases


def latest_fabric_minecraft_version(
    project_id: str,
    release_dates: dict[str, str],
    fetcher: Callable[[str], object] = fetch_json,
) -> str:
    query = urlencode(
        {"loaders": json.dumps(["fabric"]), "include_changelog": "false"}
    )
    payload = fetcher(f"project/{quote(project_id, safe='')}/version?{query}")
    if not isinstance(payload, list):
        raise CatalogError(f"Modrinth returned invalid versions for {project_id}")

    supported: set[str] = set()
    for version in payload:
        if not isinstance(version, dict):
            continue
        if version.get("version_type") not in {"release", "beta", "alpha"}:
            continue
        if version.get("status") not in {None, "listed", "archived"}:
            continue
        loaders = version.get("loaders", [])
        if not isinstance(loaders, list) or "fabric" not in loaders:
            continue
        game_versions = version.get("game_versions", [])
        if isinstance(game_versions, list):
            supported.update(
                value
                for value in game_versions
                if isinstance(value, str) and value in release_dates
            )

    if not supported:
        return UNKNOWN
    return max(supported, key=lambda value: (release_dates[value], value))


def modrinth_project_id(mod: dict) -> str | None:
    metadata = mod.get("metadata_data", {})
    update = metadata.get("update", {}) if isinstance(metadata, dict) else {}
    modrinth = update.get("modrinth", {}) if isinstance(update, dict) else {}
    project_id = modrinth.get("mod-id") if isinstance(modrinth, dict) else None
    return project_id if isinstance(project_id, str) and project_id else None


def enrich_highest_versions(mods: list[dict]) -> tuple[dict[str, str], list[str]]:
    highest = {str(mod["slug"]): UNKNOWN for mod in mods}
    warnings: list[str] = []
    modrinth_mods = [mod for mod in mods if mod.get("source") == "modrinth"]
    non_modrinth = [
        str(mod["slug"]) for mod in mods if mod.get("source") != "modrinth"
    ]
    if non_modrinth:
        warnings.append(
            "highest Fabric Minecraft version is unknown for non-Modrinth sources: "
            + ", ".join(non_modrinth)
        )
    if not modrinth_mods:
        return highest, warnings

    try:
        release_dates = minecraft_release_dates()
    except CatalogError as exc:
        if modrinth_mods:
            warnings.append(
                f"Modrinth compatibility lookup failed for all projects: {exc}"
            )
        return highest, warnings

    failures: list[str] = []
    with ThreadPoolExecutor(max_workers=min(8, max(1, len(modrinth_mods)))) as executor:
        futures = {}
        for mod in modrinth_mods:
            project_id = modrinth_project_id(mod)
            if project_id is None:
                failures.append(str(mod["slug"]))
                continue
            future = executor.submit(
                latest_fabric_minecraft_version, project_id, release_dates
            )
            futures[future] = str(mod["slug"])
        for future in as_completed(futures):
            slug = futures[future]
            try:
                highest[slug] = future.result()
            except CatalogError:
                failures.append(slug)
    if failures:
        warnings.append(
            "Modrinth compatibility lookup failed for: " + ", ".join(sorted(failures))
        )
    return highest, warnings


def print_table(mods: list[dict], highest: dict[str, str]) -> None:
    if not mods:
        return
    headers = ("SLUG", "SIDE", "SOURCE", "MAX_MC", "MOD")
    rows = [
        (
            str(mod["slug"]),
            str(mod["side"] or ""),
            str(mod["source"]),
            highest.get(str(mod["slug"]), UNKNOWN),
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
    counts = {
        side: sum(mod["side"] == side for mod in mods)
        for side in ("server", "client", "both")
    }
    print(
        f"\nImpact: {counts['server']} server-only, "
        f"{counts['client']} client-only, {counts['both']} required on both"
    )


def command_list(pack_dir: Path) -> int:
    mods, errors, validation_warnings = validate(pack_dir.resolve())
    for mod in mods:
        try:
            mod["metadata_data"] = load_toml(pack_dir.resolve() / str(mod["metadata"]))
        except ValueError:
            mod["metadata_data"] = {}
    highest, lookup_warnings = enrich_highest_versions(mods)
    print_table(mods, highest)
    for warning in (*validation_warnings, *lookup_warnings):
        print(f"warning: {warning}", file=sys.stderr)
    for error in errors:
        print(f"error: {error}", file=sys.stderr)
    if errors:
        return 1
    print("\nPack validation passed.")
    return 0


def text_value(value: object, fallback: str = UNKNOWN) -> str:
    if not isinstance(value, str) or not value.strip():
        return fallback
    return " ".join(value.split())


def list_value(value: object) -> str:
    if not isinstance(value, list):
        return UNKNOWN
    items = [str(item) for item in value if isinstance(item, str) and item]
    return ", ".join(items) if items else UNKNOWN


def inspect_modrinth(metadata: dict) -> None:
    update = metadata.get("update", {}).get("modrinth", {})
    project_id = text_value(update.get("mod-id"), "")
    version_id = text_value(update.get("version"), "")
    if not project_id or not version_id:
        raise CatalogError("incomplete Modrinth update metadata")
    project = fetch_json(f"project/{quote(project_id, safe='')}")
    version = fetch_json(f"version/{quote(version_id, safe='')}")
    if not isinstance(project, dict) or not isinstance(version, dict):
        raise CatalogError("Modrinth returned invalid project information")

    slug = text_value(project.get("slug"), project_id)
    print(f"官网名称：{text_value(project.get('title'), text_value(metadata.get('name')))}")
    print(f"简介：{text_value(project.get('description'))}")
    print(f"官网：https://modrinth.com/mod/{slug}")
    print(f"版本页：https://modrinth.com/mod/{slug}/version/{version_id}")
    print(f"选中文件：{text_value(metadata.get('filename'))}")
    print(f"模组版本：{text_value(version.get('version_number'))}")
    print(f"Minecraft：{list_value(version.get('game_versions'))}")
    print(f"加载器：{list_value(version.get('loaders'))}")
    print(f"发布通道：{text_value(version.get('version_type'))}")
    print(f"官方环境：{text_value(version.get('environment'))}")


def inspect_non_modrinth(metadata: dict, source: str) -> None:
    update = metadata.get("update", {})
    download = metadata.get("download", {})
    print(f"名称：{text_value(metadata.get('name'))}")
    print(f"来源：{source}")
    if source == "curseforge":
        curseforge = update.get("curseforge", {}) if isinstance(update, dict) else {}
        project_id = curseforge.get("project-id") if isinstance(curseforge, dict) else None
        if isinstance(project_id, int) or (isinstance(project_id, str) and project_id):
            print(f"官网：https://www.curseforge.com/projects/{project_id}")
        else:
            print("官网：unknown")
    else:
        print(f"原始链接：{text_value(download.get('url'))}")
    print(f"选中文件：{text_value(metadata.get('filename'))}")
    print("最高 Fabric Minecraft 版本：unknown")
    print("官方安装环境：unknown；请打开上述来源自行确认 side。")


def command_inspect(pack_dir: Path, metadata_path: str) -> int:
    pack_dir = pack_dir.resolve()
    path = (pack_dir / metadata_path).resolve()
    try:
        path.relative_to(pack_dir)
    except ValueError as exc:
        raise CatalogError("metadata path escapes the pack directory") from exc
    try:
        metadata = load_toml(path)
    except ValueError as exc:
        raise CatalogError(str(exc)) from exc

    update = metadata.get("update", {})
    download = metadata.get("download", {})
    if isinstance(update, dict) and "modrinth" in update:
        inspect_modrinth(metadata)
    elif (
        (isinstance(update, dict) and "curseforge" in update)
        or (
            isinstance(download, dict)
            and download.get("mode") == "metadata:curseforge"
        )
    ):
        inspect_non_modrinth(metadata, "curseforge")
    else:
        inspect_non_modrinth(metadata, "external")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    list_parser = subparsers.add_parser("list")
    list_parser.add_argument("pack_dir", nargs="?", default="pack", type=Path)
    inspect_parser = subparsers.add_parser("inspect")
    inspect_parser.add_argument("pack_dir", type=Path)
    inspect_parser.add_argument("metadata")
    args = parser.parse_args()

    try:
        if args.command == "list":
            return command_list(args.pack_dir)
        return command_inspect(args.pack_dir, args.metadata)
    except CatalogError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
