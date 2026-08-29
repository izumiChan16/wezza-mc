from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
import stat
import tempfile
import unittest
from unittest import mock

from tools import world_control


class WorldControlTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="wezza-world-test-")
        self.root = Path(self.temp_dir.name)
        (self.root / "runtime" / "data" / "world").mkdir(parents=True)
        self.env_file = self.root / ".env"
        self.env_file.write_text(
            "EULA=TRUE\nWORLD_NAME=world\nWORLD_SEED=\nKEEP_ME=unchanged\n",
            encoding="utf-8",
        )
        self.env_file.chmod(0o640)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def config(self) -> world_control.WorldConfig:
        return world_control.load_config(self.root)

    def test_status_reports_existing_world_and_random_seed(self) -> None:
        world = self.root / "runtime" / "data" / "world"
        (world / "level.dat").write_bytes(b"test")
        output = StringIO()
        with redirect_stdout(output):
            self.assertEqual(world_control.command_status(self.config()), 0)
        text = output.getvalue()
        self.assertIn("World state: present (level.dat found)", text)
        self.assertIn("Next generation seed: random (WORLD_SEED is empty)", text)

    def test_reset_archives_world_and_preserves_other_env_values(self) -> None:
        world = self.root / "runtime" / "data" / "world"
        (world / "level.dat").write_bytes(b"test world")
        (world / "region").mkdir()
        old_mode = stat.S_IMODE(self.env_file.stat().st_mode)

        output = StringIO()
        with redirect_stdout(output):
            self.assertEqual(world_control.command_reset(self.config(), -123), 0)

        self.assertFalse(world.exists())
        archives = list((self.root / "runtime" / "world-archive").iterdir())
        self.assertEqual(len(archives), 1)
        self.assertEqual((archives[0] / "level.dat").read_bytes(), b"test world")
        env_text = self.env_file.read_text(encoding="utf-8")
        self.assertIn("WORLD_SEED=-123\n", env_text)
        self.assertIn("KEEP_ME=unchanged\n", env_text)
        self.assertEqual(stat.S_IMODE(self.env_file.stat().st_mode), old_mode)
        self.assertIn("Archived previous world:", output.getvalue())

    def test_random_reset_without_world_appends_seed_setting(self) -> None:
        world = self.root / "runtime" / "data" / "world"
        for child in world.iterdir():
            if child.is_dir():
                child.rmdir()
            else:
                child.unlink()
        world.rmdir()
        self.env_file.write_text("EULA=TRUE\nKEEP_ME=unchanged\n", encoding="utf-8")

        with redirect_stdout(StringIO()):
            self.assertEqual(world_control.command_reset(self.config(), None), 0)
        self.assertFalse(world.exists())
        self.assertIn("WORLD_SEED=\n", self.env_file.read_text(encoding="utf-8"))
        self.assertFalse((self.root / "runtime" / "world-archive").exists())

    def test_reset_rolls_world_back_when_env_update_fails(self) -> None:
        world = self.root / "runtime" / "data" / "world"
        (world / "level.dat").write_bytes(b"must survive")
        config = self.config()
        with mock.patch.object(
            world_control,
            "atomic_set_seed",
            side_effect=world_control.WorldControlError("test failure"),
        ):
            with self.assertRaises(world_control.WorldControlError):
                world_control.command_reset(config, 42)
        self.assertTrue(world.is_dir())
        self.assertEqual((world / "level.dat").read_bytes(), b"must survive")
        self.assertEqual(list((self.root / "runtime" / "world-archive").iterdir()), [])

    def test_invalid_seed_and_world_name_are_rejected(self) -> None:
        self.assertEqual(
            world_control.parse_seed(str(world_control.MIN_SEED)), world_control.MIN_SEED
        )
        self.assertEqual(
            world_control.parse_seed(str(world_control.MAX_SEED)), world_control.MAX_SEED
        )
        for value in (
            "not-a-number",
            str(world_control.MIN_SEED - 1),
            str(world_control.MAX_SEED + 1),
        ):
            with self.assertRaises(world_control.WorldControlError):
                world_control.parse_seed(value)
        for value in ("../outside", "", ".", "..", "world/name", "a" * 65):
            with self.assertRaises(world_control.WorldControlError):
                world_control.validate_world_name(value)

    def test_cli_reset_requires_confirmation(self) -> None:
        before = self.env_file.read_text(encoding="utf-8")
        with redirect_stderr(StringIO()):
            result = world_control.main(["reset", "--root", str(self.root), "--seed", "1"])
        self.assertEqual(result, 1)
        self.assertEqual(self.env_file.read_text(encoding="utf-8"), before)
        self.assertTrue((self.root / "runtime" / "data" / "world").is_dir())


if __name__ == "__main__":
    unittest.main()
