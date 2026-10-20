"""Back up the h21 database and avatars into a dated archive."""

from __future__ import annotations

import argparse
import sqlite3
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from h21.config import _data_dir

ARCHIVE_PREFIX = "h21-"


def create_backup(data_dir: Path, backup_dir: Path) -> Path:
    """Write a consistent copy of the database, plus the avatars, to one archive.

    The database is copied with SQLite's backup API, which is safe while the
    server is running.
    """
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    archive_path = backup_dir.joinpath(f"{ARCHIVE_PREFIX}{stamp}.tar.gz")
    with tempfile.TemporaryDirectory() as temporary_directory:
        snapshot_path = Path(temporary_directory).joinpath("h21.db")
        source = sqlite3.connect(data_dir.joinpath("h21.db"))
        snapshot = sqlite3.connect(snapshot_path)
        with snapshot:
            source.backup(snapshot)
        snapshot.close()
        source.close()
        with tarfile.open(archive_path, "w:gz") as archive:
            archive.add(snapshot_path, arcname="h21.db")
            avatars_dir = data_dir.joinpath("avatars")
            if avatars_dir.is_dir():
                archive.add(avatars_dir, arcname="avatars")
    return archive_path


def prune_backups(backup_dir: Path, keep: int) -> list[Path]:
    """Delete all but the newest `keep` archives. Returns the deleted paths."""
    archives = sorted(backup_dir.glob(f"{ARCHIVE_PREFIX}*.tar.gz"))
    stale = archives[:-keep] if keep > 0 else archives
    for path in stale:
        path.unlink()
    return stale


def main() -> None:
    parser = argparse.ArgumentParser(description="Back up the h21 database and avatars")
    parser.add_argument("backup_dir", type=Path, help="Directory for the backup archives")
    parser.add_argument("--keep", type=int, default=10, help="Archives to keep (default: 10)")
    args = parser.parse_args()

    archive_path = create_backup(_data_dir(), args.backup_dir)
    print(f"Backed up to {archive_path}")
    for path in prune_backups(args.backup_dir, args.keep):
        print(f"Removed old backup {path.name}")


if __name__ == "__main__":
    main()
