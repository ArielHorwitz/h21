from __future__ import annotations

from datetime import date
from pathlib import Path


class Puzzle:
    def __init__(self, solutions_file: Path, start_date: date) -> None:
        self._start_date = start_date
        self._solutions = self._load_solutions(solutions_file)

    @staticmethod
    def _load_solutions(path: Path) -> list[str]:
        lines = [
            line.strip()
            for line in path.read_text().splitlines()
            if line.strip()
        ]
        if not lines:
            raise ValueError(f"No solutions found in {path}")
        return lines

    def get_today_solution(self) -> str:
        days_elapsed = (date.today() - self._start_date).days
        index = days_elapsed % len(self._solutions)
        return self._solutions[index]
