"""Delete h21 state files (database and logs) from the data directory."""

from __future__ import annotations

from h21.config import _data_dir


def main() -> None:
    data_dir = _data_dir()
    if not data_dir.exists():
        print(f"Nothing to remove — {data_dir} does not exist.")
        return

    removed = []
    for path in sorted(data_dir.iterdir()):
        print(f"Removing {path}")
        path.unlink()
        removed.append(path.name)

    if removed:
        print(f"Removed {len(removed)} file(s) from {data_dir}.")
    else:
        print(f"No files found in {data_dir}.")
