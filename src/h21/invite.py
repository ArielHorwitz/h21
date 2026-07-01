"""Generate an invite code for account registration."""

from __future__ import annotations

import argparse

from h21.config import load_config
from h21.db import GameDatabase


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate an invite code")
    parser.add_argument("--alias", default=None, help="Optional label for this invite")
    parser.add_argument("--uses", type=int, default=1, help="Number of allowed uses (default: 1)")
    parser.add_argument("--role", default="user", choices=["user", "dev"],
                        help="Role granted to accounts using this invite (default: user)")
    parser.add_argument("--question-limit", type=int, default=None,
                        help="Daily question limit for accounts using this invite (default: 105)")
    parser.add_argument("--topic-limit", type=int, default=None,
                        help="Daily topic suggestion limit for accounts using this invite (default: 1)")
    args = parser.parse_args()

    config = load_config()
    database = GameDatabase(config.db_path)
    database.ensure_schema()
    code = database.create_invite(
        alias=args.alias, uses=args.uses, role=args.role,
        daily_question_limit=args.question_limit,
        daily_topic_limit=args.topic_limit,
    )
    database.close()
    print(code)
