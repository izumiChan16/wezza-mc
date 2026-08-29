#!/usr/bin/env python3
"""Build a self-updating Prism Launcher instance from the Packwiz source."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import tempfile
import tomllib
import urllib.request
import zipfile


BOOTSTRAP_URL = (
    "https://github.com/packwiz/packwiz-installer-bootstrap/releases/download/"
    "v0.0.3/packwiz-installer-bootstrap.jar"
)
BOOTSTRAP_SHA256 = "a8fbb24dc604278e97f4688e82d3d91a318b98efc08d5dbfcbcbcab6443d116c"


def fetch_bootstrap(destination: Path) -> None:
    request = urllib.request.Request(BOOTSTRAP_URL, headers={"User-Agent": "wezza-mc-builder/1"})
    with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310 - pinned URL and hash
        destination.write_bytes(response.read())


def verify_bootstrap(path: Path) -> None:
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != BOOTSTRAP_SHA256:
        raise SystemExit(f"bootstrap checksum mismatch: expected {BOOTSTRAP_SHA256}, got {actual}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pack-dir", type=Path, default=Path("pack"))
    parser.add_argument("--pack-url", required=True)
    parser.add_argument("--output", type=Path, default=Path("dist/wezza-mc-prism.zip"))
    parser.add_argument("--bootstrap-file", type=Path)
    args = parser.parse_args()

    if not args.pack_url.startswith("https://"):
        raise SystemExit("--pack-url must be an HTTPS URL")
    if not args.pack_url.endswith("/pack.toml"):
        raise SystemExit("--pack-url must end in /pack.toml")

    pack = tomllib.loads((args.pack_dir / "pack.toml").read_text(encoding="utf-8"))
    minecraft = pack["versions"]["minecraft"]
    fabric = pack["versions"]["fabric"]
    pack_name = pack["name"]

    with tempfile.TemporaryDirectory(prefix="wezza-prism-") as temp_name:
        root = Path(temp_name)
        minecraft_dir = root / ".minecraft"
        minecraft_dir.mkdir()
        bootstrap = minecraft_dir / "packwiz-installer-bootstrap.jar"
        if args.bootstrap_file:
            bootstrap.write_bytes(args.bootstrap_file.read_bytes())
        else:
            fetch_bootstrap(bootstrap)
        verify_bootstrap(bootstrap)

        (root / "instance.cfg").write_text(
            "\n".join(
                [
                    f"name={pack_name}",
                    "InstanceType=OneSix",
                    "MCLaunchMethod=LauncherPart",
                    "OverrideCommands=true",
                    (
                        "PreLaunchCommand=\\\"$INST_JAVA\\\" -jar "
                        f"packwiz-installer-bootstrap.jar {args.pack_url}"
                    ),
                    "OverrideMemory=true",
                    "MinMemAlloc=2048",
                    "MaxMemAlloc=6144",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        (root / "mmc-pack.json").write_text(
            json.dumps(
                {
                    "components": [
                        {"important": True, "uid": "net.minecraft", "version": minecraft},
                        {"uid": "net.fabricmc.fabric-loader", "version": fabric},
                    ],
                    "formatVersion": 1,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        (minecraft_dir / "PACKWIZ-README.txt").write_text(
            "This instance updates from the server's Packwiz manifest before every launch.\n"
            "Do not remove packwiz-installer-bootstrap.jar or the pre-launch command.\n",
            encoding="utf-8",
        )

        args.output.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(args.output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(root.rglob("*")):
                if path.is_file():
                    archive.write(path, path.relative_to(root).as_posix())

    print(f"Built {args.output} for {minecraft} / Fabric {fabric}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
