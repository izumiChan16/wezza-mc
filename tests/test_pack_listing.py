from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import unittest

from tools import validate_pack


ROOT = Path(__file__).resolve().parents[1]


class PackListingTests(unittest.TestCase):
    def test_validator_exposes_metadata_slug(self) -> None:
        mods, errors, _warnings = validate_pack.validate(ROOT / "pack")
        self.assertFalse(errors)
        self.assertTrue(mods)
        badoptimizations = next(
            mod for mod in mods if mod["slug"] == "badoptimizations"
        )
        self.assertEqual(badoptimizations["slug"], "badoptimizations")
        self.assertEqual(
            badoptimizations["metadata"], "mods/badoptimizations.pw.toml"
        )

    def test_cli_table_contains_slug_header_and_known_slug(self) -> None:
        result = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "validate_pack.py"), str(ROOT / "pack")],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertIn("SLUG", result.stdout.splitlines()[0])
        self.assertIn("refined-storage", result.stdout)

    def test_bare_mod_command_is_a_listing_alias(self) -> None:
        env = {
            **os.environ,
            "MCCTL_MODRINTH_API_BASE": "http://127.0.0.1:9",
        }
        result = subprocess.run(
            [str(ROOT / "mcctl"), "mod"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
            env=env,
        )
        self.assertTrue(result.stdout.startswith("SLUG"))
        self.assertIn("MAX_MC", result.stdout.splitlines()[0])


if __name__ == "__main__":
    unittest.main()
