from __future__ import annotations

import json
import re
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
        """)
        self._migrate_add_explanation_column()
        self._migrate_daily_puzzles_composite_key()
        self._migrate_games_topic_difficulty()
        self._migrate_add_hints_column()
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
        self, puzzle_date: date, topic_slug: str, difficulty: str
    ) -> int:
        now = _utcnow_iso()
        cursor = self._connection.execute(
            "INSERT INTO games (date, topic_slug, difficulty, started_at) VALUES (?, ?, ?, ?)",
            (puzzle_date.isoformat(), topic_slug, difficulty, now),
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

    def get_history(self) -> list[dict[str, Any]]:
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

    def close(self) -> None:
        self._connection.close()


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
