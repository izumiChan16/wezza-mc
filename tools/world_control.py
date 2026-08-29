#!/usr/bin/env python3
"""Safe world inspection and reset helpers for mcctl.

The command deliberately handles only filesystem state.  mcctl is responsible
for checking Docker/service state and creating the offline backup first.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
import os
from pathlib import Path
import re
import shutil
import stat
import sys
import tempfile


WORLD_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
MIN_SEED = -(1 << 63)
MAX_SEED = (1 << 63) - 1


class WorldControlError(ValueError):
    """An actionable configuration or filesystem error."""


@dataclass(frozen=True)
class WorldConfig:
    root: Path
    env_file: Path
    data_dir: Path
    archive_dir: Path
    world_name: str
    configured_seed: int | None

    @property
    def world_dir(self) -> Path:
        return self.data_dir / self.world_name


def parse_env_value(raw: str) -> str:
    value = raw.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        raise WorldControlError(f"Missing {path}; run './mcctl init' first.")
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise WorldControlError(f"Cannot read {path}: {exc}") from exc
    for line in lines:
        match = re.match(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$", line)
        if match:
            values[match.group(1)] = parse_env_value(match.group(2))
    return values


def validate_world_name(value: str) -> str:
    if not WORLD_NAME_RE.fullmatch(value) or value in {".", ".."}:
        raise WorldControlError(
            "WORLD_NAME must be a single safe directory name (letters, numbers, "
            "dot, underscore, or hyphen; maximum 64 characters)."
        )
    return value


def parse_seed(value: str) -> int:
    try:
        seed = int(value, 10)
    except ValueError as exc:
        raise WorldControlError(
            "WORLD_SEED and --seed must be a signed 64-bit integer."
        ) from exc
    if not MIN_SEED <= seed <= MAX_SEED:
        raise WorldControlError(
            "WORLD_SEED and --seed must be between "
            f"{MIN_SEED} and {MAX_SEED}."
        )
    return seed


def load_config(root: Path) -> WorldConfig:
    root = root.resolve()
    env_file = root / ".env"
    values = read_env(env_file)
    world_name = validate_world_name(values.get("WORLD_NAME", "world") or "world")
    raw_seed = values.get("WORLD_SEED", "")
    configured_seed = parse_seed(raw_seed) if raw_seed else None
    runtime_dir = root / "runtime"
    data_dir = root / "runtime" / "data"
    archive_dir = root / "runtime" / "world-archive"
    if runtime_dir.is_symlink():
        raise WorldControlError(f"Refusing to use symlinked runtime directory: {runtime_dir}")
    if data_dir.is_symlink():
        raise WorldControlError(f"Refusing to use symlinked data directory: {data_dir}")
    if archive_dir.is_symlink():
        raise WorldControlError(f"Refusing to use symlinked archive directory: {archive_dir}")
    return WorldConfig(
        root=root,
        env_file=env_file,
        data_dir=data_dir,
        archive_dir=archive_dir,
        world_name=world_name,
        configured_seed=configured_seed,
    )


def relative_path(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


def directory_size(path: Path) -> int:
    total = 0
    for item in path.rglob("*"):
        try:
            if item.is_file() and not item.is_symlink():
                total += item.stat().st_size
        except OSError:
            continue
    return total


def human_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if value < 1024 or unit == "TiB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{size} B"


def configured_seed_text(seed: int | None) -> str:
    if seed is None:
        return "random (WORLD_SEED is empty)"
    return str(seed)


def command_status(config: WorldConfig) -> int:
    world = config.world_dir
    invalid_state = False
    if world.is_symlink():
        state = "refused: world path is a symlink"
        size = "unknown"
        modified = "unknown"
        invalid_state = True
    elif not world.exists():
        state = "not created"
        size = "0 B"
        modified = "-"
    elif not world.is_dir():
        state = "refused: world path is not a directory"
        size = "unknown"
        modified = "unknown"
        invalid_state = True
    else:
        level_dat = world / "level.dat"
        state = (
            "present (level.dat found)"
            if level_dat.is_file()
            else "present (level.dat missing)"
        )
        size = human_size(directory_size(world))
        try:
            modified = datetime.fromtimestamp(world.stat().st_mtime).astimezone().strftime(
                "%Y-%m-%d %H:%M:%S %Z"
            )
        except OSError:
            modified = "unknown"

    archives: list[Path] = []
    if config.archive_dir.is_dir():
        try:
            archives = sorted(
                (item for item in config.archive_dir.iterdir() if item.is_dir()),
                key=lambda item: item.stat().st_mtime,
                reverse=True,
            )
        except OSError as exc:
            raise WorldControlError(
                f"Cannot inspect archive directory {config.archive_dir}: {exc}"
            ) from exc

    print(f"World name: {config.world_name}")
    print(f"World path: {relative_path(world, config.root)}")
    print(f"World state: {state}")
    print(f"World size: {size}")
    print(f"World modified: {modified}")
    print(f"Next generation seed: {configured_seed_text(config.configured_seed)}")
    print(f"World archives: {len(archives)}")
    print(f"Archive path: {relative_path(config.archive_dir, config.root)}")
    if archives:
        print("Recent archives:")
        for archive in archives[:5]:
            print(f"  - {archive.name}")
    return 1 if invalid_state else 0


def replace_env_value(text: str, key: str, value: str) -> str:
    lines = text.splitlines(keepends=True)
    assignment = f"{key}={value}\n"
    replaced = False
    output: list[str] = []
    pattern = re.compile(rf"^\s*{re.escape(key)}\s*=")
    for line in lines:
        if pattern.match(line):
            newline = "\r\n" if line.endswith("\r\n") else "\n"
            output.append(f"{key}={value}{newline}")
            replaced = True
        else:
            output.append(line)
    if not replaced:
        if output and not output[-1].endswith(("\n", "\r")):
            output.append("\n")
        output.append(assignment)
    return "".join(output)


def atomic_set_seed(env_file: Path, seed: int | None) -> None:
    if env_file.is_symlink():
        raise WorldControlError(
            f"Refusing to replace symlinked configuration file: {env_file}"
        )
    try:
        original = env_file.read_text(encoding="utf-8")
        mode = stat.S_IMODE(env_file.stat().st_mode)
    except OSError as exc:
        raise WorldControlError(f"Cannot read {env_file}: {exc}") from exc

    updated = replace_env_value(original, "WORLD_SEED", "" if seed is None else str(seed))
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=env_file.parent,
            prefix=f".{env_file.name}.mcctl-",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(updated)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, env_file)
        temporary = None
        try:
            directory_fd = os.open(env_file.parent, os.O_RDONLY)
        except OSError:
            directory_fd = None
        if directory_fd is not None:
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
    except OSError as exc:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise WorldControlError(f"Cannot atomically update {env_file}: {exc}") from exc


def archive_target(config: WorldConfig) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = config.archive_dir / f"{stamp}-{config.world_name}"
    suffix = 1
    while target.exists() or target.is_symlink():
        target = config.archive_dir / f"{stamp}-{config.world_name}-{suffix:02d}"
        suffix += 1
    return target


def command_reset(config: WorldConfig, seed: int | None) -> int:
    world = config.world_dir
    if world.is_symlink():
        raise WorldControlError(f"Refusing to reset symlinked world path: {world}")
    if world.exists() and not world.is_dir():
        raise WorldControlError(f"Refusing to reset non-directory world path: {world}")

    moved_to: Path | None = None
    if world.exists():
        try:
            config.archive_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise WorldControlError(
                f"Could not create archive directory {config.archive_dir}: {exc}"
            ) from exc
        moved_to = archive_target(config)
        try:
            shutil.move(str(world), str(moved_to))
        except OSError as exc:
            raise WorldControlError(f"Could not archive {world}: {exc}") from exc

    try:
        atomic_set_seed(config.env_file, seed)
    except WorldControlError:
        if moved_to is not None and not world.exists():
            try:
                shutil.move(str(moved_to), str(world))
            except OSError as rollback_exc:
                raise WorldControlError(
                    f"Configuration update failed and rollback also failed; "
                    f"the old world is at {moved_to}: {rollback_exc}"
                ) from rollback_exc
        raise

    print("World reset prepared; the server was not started.")
    if moved_to is None:
        print("Previous world: none (a new world will be created on next start)")
    else:
        print(f"Archived previous world: {relative_path(moved_to, config.root)}")
    print(f"Next generation seed: {configured_seed_text(seed)}")
    print("Run './mcctl world status' and then './mcctl start' when ready.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect or safely reset a Minecraft world.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    status = subparsers.add_parser("status", help="show the configured world and filesystem state")
    status.add_argument("--root", type=Path, default=Path("."))

    validate = subparsers.add_parser("validate", help="validate world-related .env settings")
    validate.add_argument("--root", type=Path, default=Path("."))

    validate_seed = subparsers.add_parser("validate-seed", help="validate a signed 64-bit seed")
    validate_seed.add_argument("--seed", required=True, metavar="INTEGER")

    reset = subparsers.add_parser("reset", help="archive the current world and configure its next seed")
    reset.add_argument("--root", type=Path, default=Path("."))
    seed_group = reset.add_mutually_exclusive_group(required=True)
    seed_group.add_argument("--seed", metavar="INTEGER", help="signed 64-bit generation seed")
    seed_group.add_argument("--random", action="store_true", help="clear WORLD_SEED for random generation")
    reset.add_argument("--confirm", action="store_true", help="confirm the destructive world reset")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "validate-seed":
            parse_seed(args.seed)
            return 0
        config = load_config(args.root)
        if args.command == "status":
            return command_status(config)
        if args.command == "validate":
            return 0
        if not args.confirm:
            raise WorldControlError("World reset requires --confirm.")
        seed = None if args.random else parse_seed(args.seed)
        return command_reset(config, seed)
    except WorldControlError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
