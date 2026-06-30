from __future__ import annotations

import hashlib
import json
import re
import secrets
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Optional


VALID_DIFFICULTIES = frozenset({"easy", "medium", "hard"})


def slugify(name: str) -> str:
    """Convert a topic name to a URL-friendly slug."""
    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"[\s-]+", "-", slug)
    return slug.strip("-")


class GameDatabase:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._connection = sqlite3.connect(db_path)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute("PRAGMA foreign_keys=ON")

    def ensure_schema(self) -> None:
        self._connection.executescript("""
            CREATE TABLE IF NOT EXISTS topics (
                slug  TEXT PRIMARY KEY,
                name  TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS daily_puzzles (
                date        TEXT NOT NULL,
                topic_slug  TEXT NOT NULL,
                difficulty  TEXT NOT NULL,
                solution    TEXT NOT NULL,
                PRIMARY KEY (date, topic_slug, difficulty),
                FOREIGN KEY (topic_slug) REFERENCES topics(slug)
            );

            CREATE TABLE IF NOT EXISTS games (
                game_id         INTEGER PRIMARY KEY AUTOINCREMENT,
                date            TEXT NOT NULL,
                topic_slug      TEXT NOT NULL DEFAULT 'western-history',
                difficulty      TEXT NOT NULL DEFAULT 'medium',
                started_at      TEXT NOT NULL,
                ended_at        TEXT,
                result          TEXT,
                questions_asked INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY (topic_slug) REFERENCES topics(slug)
            );

            CREATE TABLE IF NOT EXISTS questions (
                question_id     INTEGER PRIMARY KEY AUTOINCREMENT,
                game_id         INTEGER NOT NULL,
                question_number INTEGER NOT NULL,
                question        TEXT NOT NULL,
                answer          TEXT NOT NULL,
                explanation     TEXT NOT NULL DEFAULT '',
                asked_at        TEXT NOT NULL,
                FOREIGN KEY (game_id) REFERENCES games(game_id)
            );

            CREATE TABLE IF NOT EXISTS accounts (
                user_id     INTEGER PRIMARY KEY AUTOINCREMENT,
                username    TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role        TEXT NOT NULL DEFAULT 'user',
                blocked     INTEGER NOT NULL DEFAULT 0,
                invite_code TEXT,
                created_at  TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS invites (
                code            TEXT PRIMARY KEY,
                alias           TEXT,
                role            TEXT NOT NULL DEFAULT 'user',
                remaining_uses  INTEGER NOT NULL DEFAULT 1,
                created_at      TEXT NOT NULL
            );
        """)
        self._migrate_add_explanation_column()
        self._migrate_daily_puzzles_composite_key()
        self._migrate_games_topic_difficulty()
        self._migrate_add_hints_column()
        self._migrate_add_user_id_to_games()
        self._migrate_invites_multi_use()
        self._migrate_add_invite_code_to_accounts()
        self._migrate_add_role_columns()
        self._migrate_add_blocked_column()
        self._seed_default_topic()

    def _seed_default_topic(self) -> None:
        self._connection.execute(
            "INSERT OR IGNORE INTO topics (slug, name) VALUES (?, ?)",
            ("western-history", "Western History"),
        )
        self._connection.commit()

    def _migrate_add_explanation_column(self) -> None:
        columns = [
            row["name"]
            for row in self._connection.execute("PRAGMA table_info(questions)")
        ]
        if "explanation" not in columns:
            self._connection.execute(
                "ALTER TABLE questions ADD COLUMN explanation TEXT NOT NULL DEFAULT ''"
            )
            self._connection.commit()

    def _migrate_daily_puzzles_composite_key(self) -> None:
        """Migrate old single-key daily_puzzles to composite key if needed."""
        columns = [
            row["name"]
            for row in self._connection.execute("PRAGMA table_info(daily_puzzles)")
        ]
        if "topic_slug" in columns:
            return  # Already migrated

        # Old schema has only (date, solution). Migrate to new schema.
        self._connection.executescript("""
            ALTER TABLE daily_puzzles RENAME TO daily_puzzles_old;

            CREATE TABLE daily_puzzles (
                date        TEXT NOT NULL,
                topic_slug  TEXT NOT NULL,
                difficulty  TEXT NOT NULL,
                solution    TEXT NOT NULL,
                PRIMARY KEY (date, topic_slug, difficulty),
                FOREIGN KEY (topic_slug) REFERENCES topics(slug)
            );

            INSERT INTO daily_puzzles (date, topic_slug, difficulty, solution)
                SELECT date, 'western-history', 'medium', solution
                FROM daily_puzzles_old;

            DROP TABLE daily_puzzles_old;
        """)
        self._connection.commit()

    def _migrate_games_topic_difficulty(self) -> None:
        """Add topic_slug and difficulty columns to games if missing."""
        columns = [
            row["name"]
            for row in self._connection.execute("PRAGMA table_info(games)")
        ]
        if "topic_slug" not in columns:
            self._connection.execute(
                "ALTER TABLE games ADD COLUMN topic_slug TEXT NOT NULL DEFAULT 'western-history'"
            )
        if "difficulty" not in columns:
            self._connection.execute(
                "ALTER TABLE games ADD COLUMN difficulty TEXT NOT NULL DEFAULT 'medium'"
            )
        self._connection.commit()

    def _migrate_add_hints_column(self) -> None:
        """Add hints column to daily_puzzles if missing."""
        columns = [
            row["name"]
            for row in self._connection.execute("PRAGMA table_info(daily_puzzles)")
        ]
        if "hints" not in columns:
            self._connection.execute(
                "ALTER TABLE daily_puzzles ADD COLUMN hints TEXT NOT NULL DEFAULT '[]'"
            )
            self._connection.commit()

    # -- Topics --

    def get_all_topics(self) -> list[dict[str, str]]:
        rows = self._connection.execute(
            "SELECT slug, name FROM topics ORDER BY name"
        ).fetchall()
        return [dict(row) for row in rows]

    def add_topic(self, slug: str, name: str) -> None:
        self._connection.execute(
            "INSERT OR IGNORE INTO topics (slug, name) VALUES (?, ?)",
            (slug, name),
        )
        self._connection.commit()

    def topic_exists(self, slug: str) -> bool:
        row = self._connection.execute(
            "SELECT 1 FROM topics WHERE slug = ?", (slug,)
        ).fetchone()
        return row is not None

    # -- Puzzles --

    def record_puzzle(
        self, puzzle_date: date, topic_slug: str, difficulty: str, solution: str,
        hints: Optional[list[str]] = None,
    ) -> None:
        self._connection.execute(
            "INSERT OR IGNORE INTO daily_puzzles (date, topic_slug, difficulty, solution, hints) "
            "VALUES (?, ?, ?, ?, ?)",
            (puzzle_date.isoformat(), topic_slug, difficulty, solution,
             json.dumps(hints or [])),
        )
        self._connection.commit()

    def update_puzzle_hints(
        self, puzzle_date: date, topic_slug: str, difficulty: str, hints: list[str],
    ) -> None:
        self._connection.execute(
            "UPDATE daily_puzzles SET hints = ? "
            "WHERE date = ? AND topic_slug = ? AND difficulty = ?",
            (json.dumps(hints), puzzle_date.isoformat(), topic_slug, difficulty),
        )
        self._connection.commit()

    def get_puzzle_solution(
        self, puzzle_date: date, topic_slug: str, difficulty: str
    ) -> Optional[str]:
        row = self._connection.execute(
            "SELECT solution FROM daily_puzzles WHERE date = ? AND topic_slug = ? AND difficulty = ?",
            (puzzle_date.isoformat(), topic_slug, difficulty),
        ).fetchone()
        if row is None:
            return None
        return row["solution"]

    def get_puzzle_hints(
        self, puzzle_date: date, topic_slug: str, difficulty: str
    ) -> list[str]:
        row = self._connection.execute(
            "SELECT hints FROM daily_puzzles WHERE date = ? AND topic_slug = ? AND difficulty = ?",
            (puzzle_date.isoformat(), topic_slug, difficulty),
        ).fetchone()
        if row is None:
            return []
        return json.loads(row["hints"])

    def get_all_solutions(
        self, topic_slug: str, difficulty: str
    ) -> list[str]:
        """Return all previously used solutions for a topic+difficulty, for dedup."""
        rows = self._connection.execute(
            "SELECT solution FROM daily_puzzles "
            "WHERE topic_slug = ? AND difficulty = ? ORDER BY date",
            (topic_slug, difficulty),
        ).fetchall()
        return [row["solution"] for row in rows]

    # -- Games --

    def create_game(
        self, puzzle_date: date, topic_slug: str, difficulty: str,
        user_id: Optional[int] = None,
    ) -> int:
        now = _utcnow_iso()
        cursor = self._connection.execute(
            "INSERT INTO games (date, topic_slug, difficulty, started_at, user_id) "
            "VALUES (?, ?, ?, ?, ?)",
            (puzzle_date.isoformat(), topic_slug, difficulty, now, user_id),
        )
        self._connection.commit()
        assert cursor.lastrowid is not None
        return cursor.lastrowid

    def record_question(
        self,
        game_id: int,
        question_number: int,
        question: str,
        answer: str,
        explanation: str = "",
    ) -> None:
        now = _utcnow_iso()
        self._connection.execute(
            """
            INSERT INTO questions
                (game_id, question_number, question, answer, explanation, asked_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (game_id, question_number, question, answer, explanation, now),
        )
        self._connection.execute(
            "UPDATE games SET questions_asked = ? WHERE game_id = ?",
            (question_number, game_id),
        )
        self._connection.commit()

    def end_game(self, game_id: int, result: str) -> None:
        now = _utcnow_iso()
        self._connection.execute(
            "UPDATE games SET ended_at = ?, result = ? WHERE game_id = ?",
            (now, result, game_id),
        )
        self._connection.commit()

    def get_game(self, game_id: int) -> Optional[dict[str, Any]]:
        row = self._connection.execute(
            "SELECT game_id, date, topic_slug, difficulty, started_at, ended_at, "
            "result, questions_asked FROM games WHERE game_id = ?",
            (game_id,),
        ).fetchone()
        if row is None:
            return None
        return dict(row)

    def get_history(self, user_id: Optional[int] = None) -> list[dict[str, Any]]:
        if user_id is not None:
            games = self._connection.execute(
                """
                SELECT g.game_id, g.date, g.topic_slug, g.difficulty,
                       dp.solution, g.started_at, g.ended_at,
                       g.result, g.questions_asked
                FROM games g
                JOIN daily_puzzles dp
                    ON g.date = dp.date
                    AND g.topic_slug = dp.topic_slug
                    AND g.difficulty = dp.difficulty
                WHERE g.user_id = ?
                ORDER BY g.started_at DESC
                """,
                (user_id,),
            ).fetchall()
        else:
            games = self._connection.execute(
                """
                SELECT g.game_id, g.date, g.topic_slug, g.difficulty,
                       dp.solution, g.started_at, g.ended_at,
                       g.result, g.questions_asked
                FROM games g
                JOIN daily_puzzles dp
                    ON g.date = dp.date
                    AND g.topic_slug = dp.topic_slug
                    AND g.difficulty = dp.difficulty
                ORDER BY g.started_at DESC
                """
            ).fetchall()

        result = []
        for game in games:
            questions = self._connection.execute(
                """
                SELECT question_number, question, answer, explanation, asked_at
                FROM questions
                WHERE game_id = ?
                ORDER BY question_number
                """,
                (game["game_id"],),
            ).fetchall()

            result.append({
                "game_id": game["game_id"],
                "date": game["date"],
                "topic_slug": game["topic_slug"],
                "difficulty": game["difficulty"],
                "solution": game["solution"],
                "started_at": game["started_at"],
                "ended_at": game["ended_at"],
                "result": game["result"],
                "questions_asked": game["questions_asked"],
                "questions": [dict(question) for question in questions],
            })

        return result

    def get_topic_name(self, slug: str) -> Optional[str]:
        row = self._connection.execute(
            "SELECT name FROM topics WHERE slug = ?", (slug,)
        ).fetchone()
        if row is None:
            return None
        return row["name"]

    # -- Migrations (accounts) --

    def _migrate_add_user_id_to_games(self) -> None:
        columns = [
            row["name"]
            for row in self._connection.execute("PRAGMA table_info(games)")
        ]
        if "user_id" not in columns:
            self._connection.execute(
                "ALTER TABLE games ADD COLUMN user_id INTEGER"
            )
            self._connection.commit()

    def _migrate_invites_multi_use(self) -> None:
        columns = [
            row["name"]
            for row in self._connection.execute("PRAGMA table_info(invites)")
        ]
        if "remaining_uses" in columns:
            return
        # Old schema had used_at/used_by; new schema has alias/remaining_uses.
        self._connection.executescript("""
            ALTER TABLE invites RENAME TO invites_old;

            CREATE TABLE invites (
                code            TEXT PRIMARY KEY,
                alias           TEXT,
                remaining_uses  INTEGER NOT NULL DEFAULT 1,
                created_at      TEXT NOT NULL
            );

            INSERT INTO invites (code, remaining_uses, created_at)
                SELECT code, CASE WHEN used_at IS NOT NULL THEN 0 ELSE 1 END, created_at
                FROM invites_old;

            DROP TABLE invites_old;
        """)
        self._connection.commit()

    def _migrate_add_invite_code_to_accounts(self) -> None:
        columns = [
            row["name"]
            for row in self._connection.execute("PRAGMA table_info(accounts)")
        ]
        if "invite_code" not in columns:
            self._connection.execute(
                "ALTER TABLE accounts ADD COLUMN invite_code TEXT"
            )
            self._connection.commit()

    def _migrate_add_role_columns(self) -> None:
        account_columns = [
            row["name"]
            for row in self._connection.execute("PRAGMA table_info(accounts)")
        ]
        if "role" not in account_columns:
            self._connection.execute(
                "ALTER TABLE accounts ADD COLUMN role TEXT NOT NULL DEFAULT 'user'"
            )
        invite_columns = [
            row["name"]
            for row in self._connection.execute("PRAGMA table_info(invites)")
        ]
        if "role" not in invite_columns:
            self._connection.execute(
                "ALTER TABLE invites ADD COLUMN role TEXT NOT NULL DEFAULT 'user'"
            )
        self._connection.commit()

    def _migrate_add_blocked_column(self) -> None:
        columns = [
            row["name"]
            for row in self._connection.execute("PRAGMA table_info(accounts)")
        ]
        if "blocked" not in columns:
            self._connection.execute(
                "ALTER TABLE accounts ADD COLUMN blocked INTEGER NOT NULL DEFAULT 0"
            )
            self._connection.commit()

    # -- Accounts --

    @staticmethod
    def _hash_password(password: str) -> str:
        salt = secrets.token_hex(16)
        digest = hashlib.sha256((salt + password).encode()).hexdigest()
        return f"{salt}:{digest}"

    @staticmethod
    def _verify_password(password: str, password_hash: str) -> bool:
        salt, digest = password_hash.split(":", 1)
        return hashlib.sha256((salt + password).encode()).hexdigest() == digest

    def create_account(
        self, username: str, password: str,
        role: str = "user", invite_code: Optional[str] = None,
    ) -> int:
        now = _utcnow_iso()
        password_hash = self._hash_password(password)
        cursor = self._connection.execute(
            "INSERT INTO accounts (username, password_hash, role, invite_code, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (username, password_hash, role, invite_code, now),
        )
        self._connection.commit()
        assert cursor.lastrowid is not None
        return cursor.lastrowid

    def get_account_by_username(self, username: str) -> Optional[dict[str, Any]]:
        row = self._connection.execute(
            "SELECT user_id, username, password_hash, role, blocked, created_at "
            "FROM accounts WHERE username = ?",
            (username,),
        ).fetchone()
        if row is None:
            return None
        return dict(row)

    def get_account_by_id(self, user_id: int) -> Optional[dict[str, Any]]:
        row = self._connection.execute(
            "SELECT user_id, username, role, blocked, invite_code, created_at "
            "FROM accounts WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        if row is None:
            return None
        return dict(row)

    def get_all_accounts(self) -> list[dict[str, Any]]:
        rows = self._connection.execute(
            "SELECT user_id, username, role, blocked, invite_code, created_at "
            "FROM accounts ORDER BY created_at DESC"
        ).fetchall()
        return [dict(row) for row in rows]

    def set_account_blocked(self, user_id: int, blocked: bool) -> bool:
        cursor = self._connection.execute(
            "UPDATE accounts SET blocked = ? WHERE user_id = ?",
            (1 if blocked else 0, user_id),
        )
        self._connection.commit()
        return cursor.rowcount > 0

    def authenticate(self, username: str, password: str) -> Optional[int]:
        """Return user_id if credentials are valid, else None."""
        account = self.get_account_by_username(username)
        if account is None:
            return None
        if not self._verify_password(password, account["password_hash"]):
            return None
        return account["user_id"]

    # -- Invites --

    def create_invite(
        self, alias: Optional[str] = None, uses: int = 1, role: str = "user",
    ) -> str:
        code = secrets.token_hex(4).upper()
        now = _utcnow_iso()
        self._connection.execute(
            "INSERT INTO invites (code, alias, role, remaining_uses, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (code, alias, role, uses, now),
        )
        self._connection.commit()
        return code

    def get_invite(self, code: str) -> Optional[dict[str, Any]]:
        row = self._connection.execute(
            "SELECT code, alias, role, remaining_uses, created_at FROM invites WHERE code = ?",
            (code,),
        ).fetchone()
        if row is None:
            return None
        return dict(row)

    def get_all_invites(self) -> list[dict[str, Any]]:
        rows = self._connection.execute(
            "SELECT code, alias, role, remaining_uses, created_at "
            "FROM invites ORDER BY created_at DESC"
        ).fetchall()
        return [dict(row) for row in rows]

    def consume_invite(self, code: str) -> Optional[str]:
        """Decrement remaining uses. Returns the invite's role if valid, else None."""
        row = self._connection.execute(
            "SELECT remaining_uses, role FROM invites WHERE code = ?", (code,)
        ).fetchone()
        if row is None:
            return None
        if row["remaining_uses"] <= 0:
            return None
        self._connection.execute(
            "UPDATE invites SET remaining_uses = remaining_uses - 1 WHERE code = ?",
            (code,),
        )
        self._connection.commit()
        return row["role"]

    def delete_invite(self, code: str) -> bool:
        cursor = self._connection.execute(
            "DELETE FROM invites WHERE code = ?", (code,),
        )
        self._connection.commit()
        return cursor.rowcount > 0

    def close(self) -> None:
        self._connection.close()


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
