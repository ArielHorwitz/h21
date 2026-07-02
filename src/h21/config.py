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
    openai_api_key: str
    model: str
    reasoning_effort: Optional[str]
    db_path: Path
    log_path: Path
    invite_request_hint: str


def load_config() -> Config:
    config_path = _config_dir() / "config.toml"
    if config_path.exists():
        raw = tomllib.loads(config_path.read_text())
    else:
        raw = {}

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

    model = raw.get("model", "gpt-5.4-nano")
    reasoning_effort = raw.get("reasoning_effort", "high")
    invite_request_hint = raw.get("invite_request_hint", "Email")

    return Config(
        openai_api_key=openai_api_key,
        model=model,
        reasoning_effort=reasoning_effort,
        db_path=db_path,
        log_path=data_dir / "h21.log",
        invite_request_hint=invite_request_hint,
    )
