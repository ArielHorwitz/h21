from __future__ import annotations

import tarfile
import tempfile
import unittest
from pathlib import Path

from h21.backup import create_backup, prune_backups
from h21.db import GameDatabase


class BackupTests(unittest.TestCase):
    def test_backup_holds_the_database_and_avatars(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            data_dir = Path(temporary_directory).joinpath("data")
            data_dir.joinpath("avatars").mkdir(parents=True)
            data_dir.joinpath("avatars", "ABCD.webp").write_bytes(b"picture")
            database = GameDatabase(data_dir.joinpath("h21.db"))
            database.ensure_schema()
            database.add_topic("jazz", "Jazz")

            archive_path = create_backup(data_dir, Path(temporary_directory).joinpath("backups"))
            database.close()

            with tarfile.open(archive_path) as archive:
                self.assertIn("h21.db", archive.getnames())
                self.assertIn("avatars/ABCD.webp", archive.getnames())
                archive.extract("h21.db", Path(temporary_directory).joinpath("restored"))
            restored = GameDatabase(Path(temporary_directory).joinpath("restored", "h21.db"))
            self.assertEqual(restored.get_topic("jazz")["name"], "Jazz")
            restored.close()

    def test_prune_keeps_the_newest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            backup_dir = Path(temporary_directory)
            for stamp in ("20261001T000000Z", "20261002T000000Z", "20261003T000000Z"):
                backup_dir.joinpath(f"h21-{stamp}.tar.gz").write_bytes(b"")
            removed = prune_backups(backup_dir, keep=2)
            self.assertEqual([path.name for path in removed], ["h21-20261001T000000Z.tar.gz"])


if __name__ == "__main__":
    unittest.main()
