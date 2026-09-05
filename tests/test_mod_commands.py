from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ModCommandTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="wezza-mod-command-test-")
        self.root = Path(self.temp_dir.name)
        shutil.copy2(ROOT / "mcctl", self.root / "mcctl")
        (self.root / "pack" / "mods").mkdir(parents=True)
        (self.root / "pack" / "pack.toml").write_text(
            'name = "Test"\n[versions]\nminecraft = "26.1.2"\nfabric = "0.19.3"\n',
            encoding="utf-8",
        )
        (self.root / "pack" / "index.toml").write_text(
            'hash-format = "sha256"\nfiles = []\n', encoding="utf-8"
        )
        tools = self.root / "tools"
        tools.mkdir()
        (tools / "validate_pack.py").write_text(
            "#!/usr/bin/env python3\nraise SystemExit(0)\n", encoding="utf-8"
        )
        (tools / "mod_catalog.py").write_text(
            "#!/usr/bin/env python3\n"
            "import os, pathlib, sys\n"
            "metadata = pathlib.Path(sys.argv[-1]).stem.removesuffix('.pw')\n"
            "print(f'官网资料：{metadata}')\n"
            "if os.environ.get('FAIL_INSPECT') == metadata:\n"
            "    raise SystemExit(1)\n",
            encoding="utf-8",
        )

        fake_bin = self.root / "fake-bin"
        fake_bin.mkdir()
        fake_docker = fake_bin / "docker"
        fake_docker.write_text(
            "#!/usr/bin/env bash\n"
            "if [[ $1 == info ]]; then exit 0; fi\n"
            "if [[ $1 == compose && $* == *'modrinth add'* ]]; then\n"
            "  mkdir -p \"$PACK_DIR/mods\"\n"
            "  printf '%s\\n' 'name = \"Dependency\"' 'filename = \"dependency.jar\"' 'side = \"both\"' > \"$PACK_DIR/mods/dependency.pw.toml\"\n"
            "  printf '%s\\n' 'name = \"Target\"' 'filename = \"target.jar\"' 'side = \"both\"' > \"$PACK_DIR/mods/target.pw.toml\"\n"
            "fi\n"
            "exit 0\n",
            encoding="utf-8",
        )
        fake_docker.chmod(0o755)
        self.env = os.environ.copy()
        self.env["PATH"] = f"{fake_bin}:{self.env['PATH']}"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def run_add(
        self, menu_input: str, extra_env: dict[str, str] | None = None
    ) -> subprocess.CompletedProcess[str]:
        env = self.env.copy()
        if extra_env:
            env.update(extra_env)
        return subprocess.run(
            [str(self.root / "mcctl"), "mod", "add", "example"],
            cwd=self.root,
            input=menu_input,
            text=True,
            capture_output=True,
            check=False,
            env=env,
        )

    def test_add_prompts_for_target_and_dependency_sides(self) -> None:
        result = self.run_add("1\n3\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        dependency = (self.root / "pack" / "mods" / "dependency.pw.toml").read_text()
        target = (self.root / "pack" / "mods" / "target.pw.toml").read_text()
        self.assertIn('side = "client"', dependency)
        self.assertIn('side = "both"', target)
        self.assertIn("官网资料：dependency", result.stdout)
        self.assertIn("官网资料：target", result.stdout)

    def test_cancelling_any_side_keeps_real_pack_unchanged(self) -> None:
        result = self.run_add("1\nq\n")
        self.assertEqual(result.returncode, 130, result.stderr)
        self.assertFalse((self.root / "pack" / "mods" / "dependency.pw.toml").exists())
        self.assertFalse((self.root / "pack" / "mods" / "target.pw.toml").exists())
        self.assertIn("real pack was not changed", result.stdout)

    def test_failed_official_lookup_keeps_real_pack_unchanged(self) -> None:
        result = self.run_add("1\n", {"FAIL_INSPECT": "target"})
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.root / "pack" / "mods" / "dependency.pw.toml").exists())
        self.assertFalse((self.root / "pack" / "mods" / "target.pw.toml").exists())
        self.assertIn("Could not retrieve official information", result.stderr)


if __name__ == "__main__":
    unittest.main()
