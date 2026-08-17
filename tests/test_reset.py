from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from h21.reset import reset_targets


class ResetTargetTests(unittest.TestCase):
    def test_only_session_database_and_log_files_are_selected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            data_dir = Path(temporary_directory)
            expected_names = {
                "h21.db",
                "h21.db-wal",
                "h21.log",
                "h21.log.2",
                "signing_secret",
            }
            preserved_names = {"notes.txt"}
            for name in expected_names | preserved_names:
                (data_dir / name).touch()
            (data_dir / "avatars").mkdir()

            targets = reset_targets(data_dir)

            self.assertEqual({path.name for path in targets}, expected_names)
            self.assertEqual(targets[0].name, "signing_secret")
            self.assertTrue(all((data_dir / name).exists() for name in preserved_names))
            self.assertTrue((data_dir / "avatars").is_dir())


if __name__ == "__main__":
    unittest.main()
