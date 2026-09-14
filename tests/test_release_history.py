from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from tools import release_pack


def release_payload(
    version: str,
    previous: str,
    published_at: str,
    *,
    player_actions: tuple[bool, ...] = (),
    release_type: str = "small",
) -> dict:
    return {
        "schema": 1,
        "pack_version": version,
        "previous_pack_version": previous,
        "minecraft": version.rsplit("-r", 1)[0],
        "fabric_loader": "0.19.3",
        "release_type": release_type,
        "requires_reimport": release_type == "full",
        "published_at": published_at,
        "changes": [
            {
                "action": "updated",
                "player_action": player_action,
            }
            for player_action in player_actions
        ],
    }


class ReleaseHistoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="wezza-release-history-")
        self.root = Path(self.temp_dir.name)
        self.history = self.root / "releases"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def write_release(self, name: str, payload: object) -> Path:
        path = self.root / name
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_archive_builds_newest_first_index_with_change_counts(self) -> None:
        first = release_payload(
            "26.1.2-r1",
            "0.1.0",
            "2026-08-29T08:44:14+00:00",
            release_type="full",
        )
        second = release_payload(
            "26.1.2-r2",
            "26.1.2-r1",
            "2026-08-29T11:05:57+00:00",
            player_actions=(True, False, True),
        )

        release_pack.archive_release(self.write_release("first.json", first), self.history)
        index = release_pack.archive_release(
            self.write_release("current.json", second), self.history
        )

        self.assertEqual(
            [item["pack_version"] for item in index["releases"]],
            ["26.1.2-r2", "26.1.2-r1"],
        )
        self.assertEqual(index["releases"][0]["player_change_count"], 2)
        self.assertEqual(index["releases"][0]["server_change_count"], 1)
        self.assertEqual(
            json.loads((self.history / "26.1.2-r1.json").read_text()), first
        )
        self.assertEqual(
            release_pack.validate_history(self.root / "current.json", self.history),
            [],
        )

    def test_archive_rejects_different_payload_for_existing_version(self) -> None:
        original = release_payload(
            "26.1.2-r1", "0.1.0", "2026-08-29T08:44:14+00:00"
        )
        replacement = {**original, "published_at": "2026-08-30T08:44:14+00:00"}
        release_pack.archive_release(
            self.write_release("original.json", original), self.history
        )

        with self.assertRaisesRegex(ValueError, "already contains a different"):
            release_pack.archive_release(
                self.write_release("replacement.json", replacement), self.history
            )

    def test_archive_rejects_broken_version_chain_without_writing_release(self) -> None:
        first = release_payload(
            "26.1.2-r1", "0.1.0", "2026-08-29T08:44:14+00:00"
        )
        third = release_payload(
            "26.1.2-r3", "26.1.2-r2", "2026-08-30T08:44:14+00:00"
        )
        release_pack.archive_release(self.write_release("first.json", first), self.history)

        with self.assertRaisesRegex(ValueError, "previous_pack_version must be 26.1.2-r1"):
            release_pack.archive_release(
                self.write_release("third.json", third), self.history
            )
        self.assertFalse((self.history / "26.1.2-r3.json").exists())

    def test_history_validation_detects_stale_index_and_current_release(self) -> None:
        first = release_payload(
            "26.1.2-r1", "0.1.0", "2026-08-29T08:44:14+00:00"
        )
        second = release_payload(
            "26.1.2-r2", "26.1.2-r1", "2026-08-30T08:44:14+00:00"
        )
        first_path = self.write_release("first.json", first)
        release_pack.archive_release(first_path, self.history)
        release_pack.archive_release(self.write_release("second.json", second), self.history)
        (self.history / "index.json").write_text(
            '{"schema": 1, "releases": []}', encoding="utf-8"
        )

        errors = release_pack.validate_history(first_path, self.history)

        self.assertTrue(any("index does not match" in error for error in errors))
        self.assertTrue(any("latest archived release" in error for error in errors))

    def test_release_validation_rejects_naive_timestamp_and_invalid_changes(self) -> None:
        payload = release_payload(
            "26.1.2-r1", "0.1.0", "2026-08-29T08:44:14+00:00"
        )
        payload["published_at"] = "2026-08-29T08:44:14"
        payload["changes"] = [{"player_action": "yes"}]

        errors = release_pack.validate_release_data(payload)

        self.assertTrue(any("timezone-aware" in error for error in errors))
        self.assertTrue(any("player_action must be boolean" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
