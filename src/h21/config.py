from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

APP_NAME = "h21"


def _config_dir() -> Path:
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg) / APP_NAME
    return Path.home().joinpath(".config", APP_NAME)


def _data_dir() -> Path:
    xdg = os.environ.get("XDG_DATA_HOME")
    if xdg:
        return Path(xdg) / APP_NAME
    return Path.home().joinpath(".local", "share", APP_NAME)


@dataclass(frozen=True)
class Config:
    pow_difficulty: int
    openai_api_key: str
    db_path: Path
    bypass_password: Optional[str]


def load_config() -> Config:
    config_path = _config_dir() / "config.toml"
    if config_path.exists():
        raw = tomllib.loads(config_path.read_text())
    else:
        raw = {}

    pow_difficulty = int(raw.get("pow_difficulty", 20))

    openai_api_key = os.environ.get(
        "OPENAI_API_KEY", raw.get("openai_api_key", "")
    )
    if not openai_api_key:
        raise ValueError(
            f"OpenAI API key must be set in {config_path} or via "
            "OPENAI_API_KEY environment variable"
        )

    data_dir = _data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)
    db_path = data_dir / "h21.db"

    bypass_password = raw.get("bypass_password") or None

    return Config(
        pow_difficulty=pow_difficulty,
        openai_api_key=openai_api_key,
        db_path=db_path,
        bypass_password=bypass_password,
    )
