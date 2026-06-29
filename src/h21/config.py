from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from datetime import date
from pathlib import Path

CONFIG_PATH = Path("config.toml")


@dataclass(frozen=True)
class Config:
    start_date: date
    solutions_file: Path
    pow_difficulty: int
    openai_api_key: str


def load_config(path: Path = CONFIG_PATH) -> Config:
    raw = tomllib.loads(path.read_text())

    start_date = date.fromisoformat(raw["start_date"])
    solutions_file = Path(raw.get("solutions_file", "daily-solutions.txt"))
    pow_difficulty = int(raw.get("pow_difficulty", 20))

    openai_api_key = os.environ.get(
        "OPENAI_API_KEY", raw.get("openai_api_key", "")
    )
    if not openai_api_key:
        raise ValueError(
            "OpenAI API key must be set in config.toml or via OPENAI_API_KEY "
            "environment variable"
        )

    return Config(
        start_date=start_date,
        solutions_file=solutions_file,
        pow_difficulty=pow_difficulty,
        openai_api_key=openai_api_key,
    )
