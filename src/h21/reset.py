"""Delete h21 database, session secret, and logs from the data directory."""

from __future__ import annotations

import argparse
from pathlib import Path

from h21.config import _data_dir


DATABASE_FILES = ("h21.db", "h21.db-shm", "h21.db-wal")
SESSION_FILES = ("signing_secret",)
LOG_FILES = ("h21.log", "h21.log.1", "h21.log.2", "h21.log.3")


def reset_targets(data_dir: Path) -> list[Path]:
    """Return existing database, session-secret, and log reset targets."""
    return [
        data_dir / name
        # Remove the secret before the database. If secret removal fails, the
        # database remains intact and numeric user IDs cannot be rebound while
        # old session tokens are still valid.
        for name in (*SESSION_FILES, *DATABASE_FILES, *LOG_FILES)
        if (data_dir / name).is_file()
    ]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Delete h21 database, sessions, and logs (avatars are kept)",
    )
    parser.add_argument(
        "--yes", action="store_true", help="Skip the interactive confirmation",
    )
    args = parser.parse_args()

    data_dir = _data_dir()
    targets = reset_targets(data_dir)
    if not targets:
        print(f"No database, signing secret, or log files found in {data_dir}.")
        return

    if not args.yes:
        print(
            "This permanently deletes all accounts, games, invites, sessions, and logs."
        )
        answer = input("Type RESET to continue: ")
        if answer != "RESET":
            print("Reset cancelled.")
            return

    for path in targets:
        print(f"Removing {path}")
        path.unlink()
    print(f"Removed {len(targets)} file(s) from {data_dir}.")
