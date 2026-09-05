from __future__ import annotations

from contextlib import redirect_stdout
import io
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from tools import mod_catalog


class ModCatalogTests(unittest.TestCase):
    def test_highest_version_includes_mod_prereleases_but_not_mc_snapshots(self) -> None:
        release_dates = {
            "26.1.2": "2026-07-17T00:00:00Z",
            "26.2": "2026-08-18T00:00:00Z",
            "26.4": "2026-12-01T00:00:00Z",
        }

        def fetcher(path: str) -> object:
            self.assertIn("loaders=%5B%22fabric%22%5D", path)
            return [
                {
                    "version_type": "release",
                    "loaders": ["fabric"],
                    "game_versions": ["26.1.2"],
                },
                {
                    "version_type": "alpha",
                    "loaders": ["fabric"],
                    "game_versions": ["26.2", "26.3-snapshot"],
                },
                {
                    "version_type": "release",
                    "loaders": ["neoforge"],
                    "game_versions": ["26.4"],
                },
            ]

        self.assertEqual(
            mod_catalog.latest_fabric_minecraft_version(
                "project-id", release_dates, fetcher
            ),
            "26.2",
        )

    def test_minecraft_release_dates_excludes_snapshots(self) -> None:
        result = mod_catalog.minecraft_release_dates(
            lambda _path: [
                {
                    "version": "26.2",
                    "version_type": "release",
                    "date": "2026-08-18T00:00:00Z",
                },
                {
                    "version": "26.3-snapshot",
                    "version_type": "snapshot",
                    "date": "2026-09-01T00:00:00Z",
                },
            ]
        )
        self.assertEqual(result, {"26.2": "2026-08-18T00:00:00Z"})

    def test_modrinth_inspection_shows_official_side_evidence(self) -> None:
        with tempfile.TemporaryDirectory(prefix="wezza-catalog-test-") as temp:
            pack = Path(temp)
            metadata = pack / "mods" / "example.pw.toml"
            metadata.parent.mkdir()
            metadata.write_text(
                'name = "Example"\n'
                'filename = "example.jar"\n'
                'side = "both"\n'
                '[download]\n'
                'url = "https://cdn.modrinth.com/example.jar"\n'
                '[update.modrinth]\n'
                'mod-id = "project-id"\n'
                'version = "version-id"\n',
                encoding="utf-8",
            )

            responses = [
                {
                    "title": "Official Example",
                    "slug": "official-example",
                    "description": "Runs on a dedicated server.",
                },
                {
                    "version_number": "2.0.0-beta.1",
                    "game_versions": ["26.1.2"],
                    "loaders": ["fabric"],
                    "version_type": "beta",
                    "environment": "server_only",
                },
            ]
            output = io.StringIO()
            with mock.patch.object(mod_catalog, "fetch_json", side_effect=responses):
                with redirect_stdout(output):
                    result = mod_catalog.command_inspect(pack, "mods/example.pw.toml")

        self.assertEqual(result, 0)
        rendered = output.getvalue()
        self.assertIn("https://modrinth.com/mod/official-example", rendered)
        self.assertIn("发布通道：beta", rendered)
        self.assertIn("官方环境：server_only", rendered)

    def test_non_modrinth_inspection_marks_compatibility_unknown(self) -> None:
        with tempfile.TemporaryDirectory(prefix="wezza-catalog-test-") as temp:
            pack = Path(temp)
            metadata = pack / "mods" / "example.pw.toml"
            metadata.parent.mkdir()
            metadata.write_text(
                'name = "Example"\n'
                'filename = "example.jar"\n'
                'side = "both"\n'
                '[download]\n'
                'mode = "metadata:curseforge"\n'
                '[update.curseforge]\n'
                'project-id = 306612\n'
                'file-id = 1234\n',
                encoding="utf-8",
            )
            output = io.StringIO()
            with redirect_stdout(output):
                result = mod_catalog.command_inspect(pack, "mods/example.pw.toml")

        self.assertEqual(result, 0)
        rendered = output.getvalue()
        self.assertIn("https://www.curseforge.com/projects/306612", rendered)
        self.assertIn("最高 Fabric Minecraft 版本：unknown", rendered)


if __name__ == "__main__":
    unittest.main()
