from __future__ import annotations

import hashlib
import json
import re
import secrets
import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional


VALID_DIFFICULTIES = frozenset({"normal", "expert"})

# Topics created within this long carry a "New" tag on Today.
NEW_TOPIC_AGE = timedelta(days=3)


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
                slug    TEXT PRIMARY KEY,
                name    TEXT NOT NULL,
                user_id INTEGER,
                status  TEXT NOT NULL DEFAULT 'generating',
                status_detail TEXT,
                created_at    TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS puzzles (
                date        TEXT NOT NULL,
                topic_slug  TEXT NOT NULL,
                difficulty  TEXT NOT NULL,
                solution    TEXT NOT NULL,
                hints       TEXT NOT NULL DEFAULT '[]',
                PRIMARY KEY (date, topic_slug, difficulty),
                FOREIGN KEY (topic_slug) REFERENCES topics(slug)
            );

            CREATE TABLE IF NOT EXISTS pool_solutions (
                pool_id      INTEGER PRIMARY KEY AUTOINCREMENT,
                topic_slug   TEXT NOT NULL REFERENCES topics(slug),
                difficulty   TEXT NOT NULL,
                solution     TEXT NOT NULL,
                generated_at TEXT NOT NULL,
                UNIQUE(topic_slug, difficulty, solution)
            );

            CREATE TABLE IF NOT EXISTS series (
                topic_slug      TEXT NOT NULL REFERENCES topics(slug),
                difficulty      TEXT NOT NULL,
                status          TEXT NOT NULL,
                needs_attention TEXT,
                PRIMARY KEY (topic_slug, difficulty)
            );

            CREATE TABLE IF NOT EXISTS preview_solutions (
                topic_slug TEXT NOT NULL REFERENCES topics(slug),
                position   INTEGER NOT NULL,
                solution   TEXT NOT NULL,
                PRIMARY KEY (topic_slug, position)
            );

            CREATE TABLE IF NOT EXISTS pool_refills (
                refill_id   INTEGER PRIMARY KEY AUTOINCREMENT,
                topic_slug  TEXT NOT NULL REFERENCES topics(slug),
                difficulty  TEXT NOT NULL,
                generated   INTEGER NOT NULL,
                kept        INTEGER NOT NULL,
                finished_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS games (
                game_id         INTEGER PRIMARY KEY AUTOINCREMENT,
                date            TEXT NOT NULL,
                topic_slug      TEXT NOT NULL,
                difficulty      TEXT NOT NULL,
                user_id         INTEGER,
                share_code      TEXT,
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
                user_id         INTEGER,
                FOREIGN KEY (game_id) REFERENCES games(game_id)
            );

            CREATE TABLE IF NOT EXISTS hint_reveals (
                game_id         INTEGER NOT NULL,
                hint_index      INTEGER NOT NULL,
                after_question  INTEGER NOT NULL,
                revealed_at     TEXT NOT NULL,
                PRIMARY KEY (game_id, hint_index),
                FOREIGN KEY (game_id) REFERENCES games(game_id)
            );

            CREATE TABLE IF NOT EXISTS accounts (
                user_id     INTEGER PRIMARY KEY AUTOINCREMENT,
                username    TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role        TEXT NOT NULL DEFAULT 'user',
                blocked     INTEGER NOT NULL DEFAULT 0,
                daily_question_limit INTEGER NOT NULL,
                daily_topic_limit    INTEGER NOT NULL,
                invite_code TEXT,
                display_name TEXT,
                player_code  TEXT UNIQUE,
                anonymous    INTEGER NOT NULL DEFAULT 0,
                avatar_version INTEGER NOT NULL DEFAULT 0,
                avatar_generations_used INTEGER NOT NULL DEFAULT 0,
                avatar_generation_reset TEXT,
                monthly_avatar_limit INTEGER NOT NULL DEFAULT 3,
                created_at  TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS friends (
                user_id    INTEGER NOT NULL,
                friend_id  INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (user_id, friend_id),
                FOREIGN KEY (user_id) REFERENCES accounts(user_id),
                FOREIGN KEY (friend_id) REFERENCES accounts(user_id)
            );

            CREATE TABLE IF NOT EXISTS invites (
                code            TEXT PRIMARY KEY,
                alias           TEXT,
                role            TEXT NOT NULL DEFAULT 'user',
                remaining_uses  INTEGER NOT NULL DEFAULT 1,
                daily_question_limit INTEGER,
                daily_topic_limit    INTEGER,
                monthly_avatar_limit INTEGER,
                created_at      TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS daily_usage (
                user_id                INTEGER NOT NULL,
                date                   TEXT NOT NULL,
                questions_used         INTEGER NOT NULL DEFAULT 0,
                topic_suggestions_used INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (user_id, date)
            );

            CREATE TABLE IF NOT EXISTS invite_requests (
                request_id   INTEGER PRIMARY KEY AUTOINCREMENT,
                contact_info TEXT NOT NULL,
                created_at   TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS activity_log (
                log_id     INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER NOT NULL,
                action     TEXT NOT NULL,
                detail     TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES accounts(user_id)
            );
        """)

    def _generate_player_code(self, hex_bytes: int = 2) -> str:
        """Generate a unique player code. Starts at 4 hex chars, grows on exhaustion."""
        max_retries = 10
        for attempt in range(max_retries):
            code = secrets.token_hex(hex_bytes).upper()
            existing = self._connection.execute(
                "SELECT 1 FROM accounts WHERE player_code = ?", (code,)
            ).fetchone()
            if existing is None:
                return code
        # If we exhausted retries, bump length.
        return self._generate_player_code(hex_bytes + 1)

    def _generate_and_set_player_code(self, user_id: int) -> str:
        code = self._generate_player_code()
        self._connection.execute(
            "UPDATE accounts SET player_code = ? WHERE user_id = ?",
            (code, user_id),
        )
        self._connection.commit()
        return code


    # -- Topics --

    def get_all_topics(self) -> list[dict[str, str]]:
        rows = self._connection.execute(
            "SELECT slug, name FROM topics ORDER BY name"
        ).fetchall()
        return [dict(row) for row in rows]

    def get_topics_ranked(self, user_id: int, today: date) -> list[dict[str, Any]]:
        """Return playable topics sorted to surface unplayed puzzles first.

        Topics still being built are only included for the user who suggested
        them, so they can follow progress. Each topic carries its series'
        display states (see ``_series_display_state``), its preview solutions
        and whether it is new. Topics whose series have all finished sort last.

        Each topic includes a ``friends`` dict mapping difficulty to a list of
        friend avatar entries for today's puzzles.  Topics are grouped into
        tiers -- played by a friend but not the user, then unplayed by both,
        then already played by the user -- with popularity (play count plus a
        friend-activity boost) as the tiebreak within each tier.
        """
        today_str = today.isoformat()

        # All topics with their total play count.
        topic_rows = self._connection.execute(
            "SELECT t.slug, t.name, t.status, t.status_detail, t.user_id, t.created_at, "
            "COUNT(g.game_id) AS play_count "
            "FROM topics t "
            "LEFT JOIN games g ON g.topic_slug = t.slug "
            "WHERE t.status = 'ready' OR (t.status = 'generating' AND t.user_id = ?) "
            "GROUP BY t.slug, t.name",
            (user_id,),
        ).fetchall()
        new_since = (datetime.now(timezone.utc) - NEW_TOPIC_AGE).isoformat()

        topics: dict[str, dict[str, Any]] = {}
        for row in topic_rows:
            topics[row["slug"]] = {
                "slug": row["slug"],
                "name": row["name"],
                "status": row["status"],
                "status_detail": row["status_detail"],
                "suggested_by_me": row["user_id"] == user_id,
                "is_new": row["created_at"] >= new_since,
                "play_count": row["play_count"],
                "series": {},
                "preview": self.get_preview_solutions(row["slug"]),
                "friends": {},
            }
        for series_row in self._connection.execute("SELECT topic_slug, difficulty, status FROM series").fetchall():
            topic = topics.get(series_row["topic_slug"])
            if topic is None or series_row["status"] == "unavailable":
                continue
            topic["series"][series_row["difficulty"]] = self._series_display_state(
                series_row["topic_slug"], series_row["difficulty"], series_row["status"], today,
            )

        # Friend activity on today's puzzles.
        account = self._connection.execute(
            "SELECT anonymous FROM accounts WHERE user_id = ?", (user_id,)
        ).fetchone()
        is_anonymous = account is None or account["anonymous"]

        if not is_anonymous:
            friend_rows = self._connection.execute(
                "SELECT dp.topic_slug, dp.difficulty, "
                "fa.display_name, fa.player_code, fa.avatar_version "
                "FROM puzzles dp "
                "JOIN friends f ON f.user_id = ? "
                "JOIN games fg ON fg.user_id = f.friend_id "
                "  AND fg.date = dp.date "
                "  AND fg.topic_slug = dp.topic_slug "
                "  AND fg.difficulty = dp.difficulty "
                "  AND fg.result = 'win' "
                "JOIN accounts fa ON fa.user_id = f.friend_id AND fa.anonymous = 0 "
                "WHERE dp.date = ? "
                "ORDER BY fa.display_name",
                (user_id, today_str),
            ).fetchall()

            for row in friend_rows:
                topic = topics.get(row["topic_slug"])
                if topic is None:
                    continue
                difficulty = row["difficulty"]
                if difficulty not in topic["friends"]:
                    topic["friends"][difficulty] = []
                topic["friends"][difficulty].append({
                    "display_name": row["display_name"],
                    "player_code": row["player_code"],
                    "avatar_version": row["avatar_version"],
                })

        # Topics the user has already played (any difficulty) today.
        played_rows = self._connection.execute(
            "SELECT DISTINCT topic_slug FROM games "
            "WHERE user_id = ? AND date = ? AND result IS NOT NULL",
            (user_id, today_str),
        ).fetchall()
        played_slugs = {row["topic_slug"] for row in played_rows}

        friend_boost_weight = 50

        def sort_key(topic: dict[str, Any]) -> tuple[int, int, str]:
            friend_count = sum(len(v) for v in topic["friends"].values())
            score = topic["play_count"] + friend_count * friend_boost_weight
            # Tier surfaces unplayed puzzles first: friend-played (0) before
            # untouched (1) before played by the user (2), with finished
            # topics (3) last.  Popularity score (negated for descending)
            # then name break ties within a tier.
            states = [series["state"] for series in topic["series"].values()]
            if states and all(state == "finished" for state in states):
                tier = 3
            elif topic["slug"] in played_slugs:
                tier = 2
            elif friend_count > 0:
                tier = 0
            else:
                tier = 1
            return (tier, -score, topic["name"])

        return sorted(topics.values(), key=sort_key)

    def add_topic(
        self, slug: str, name: str, user_id: Optional[int] = None,
        status: str = "generating",
    ) -> bool:
        """Insert a topic. Returns False if one with that slug already exists."""
        cursor = self._connection.execute(
            "INSERT OR IGNORE INTO topics (slug, name, user_id, status, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (slug, name, user_id, status, _utcnow_iso()),
        )
        self._connection.commit()
        return cursor.rowcount == 1

    def set_topic_owner(self, slug: str, user_id: int) -> None:
        self._connection.execute("UPDATE topics SET user_id = ? WHERE slug = ?", (user_id, slug))
        self._connection.commit()

    def get_turned_down_topics(self, limit: int = 30) -> list[dict[str, Any]]:
        """Return the most recently turned-down topics, newest first."""
        rows = self._connection.execute(
            "SELECT slug, name, status_detail, created_at FROM topics "
            "WHERE status = 'failed' ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]

    def get_topic(self, slug: str) -> Optional[dict[str, Any]]:
        row = self._connection.execute(
            "SELECT slug, name, user_id, status, status_detail FROM topics WHERE slug = ?",
            (slug,),
        ).fetchone()
        return dict(row) if row is not None else None

    def get_topics_with_status(self, status: str) -> list[dict[str, Any]]:
        rows = self._connection.execute(
            "SELECT slug, name, user_id, status, status_detail FROM topics WHERE status = ?",
            (status,),
        ).fetchall()
        return [dict(row) for row in rows]

    def set_topic_status(
        self, slug: str, status: str, status_detail: Optional[str] = None,
    ) -> None:
        self._connection.execute(
            "UPDATE topics SET status = ?, status_detail = ? WHERE slug = ?",
            (status, status_detail, slug),
        )
        self._connection.commit()

    def delete_topic(self, slug: str) -> None:
        """Delete a topic that was never played, along with its pool."""
        self._connection.execute("DELETE FROM pool_solutions WHERE topic_slug = ?", (slug,))
        self._connection.execute("DELETE FROM series WHERE topic_slug = ?", (slug,))
        self._connection.execute("DELETE FROM preview_solutions WHERE topic_slug = ?", (slug,))
        self._connection.execute("DELETE FROM pool_refills WHERE topic_slug = ?", (slug,))
        self._connection.execute("DELETE FROM topics WHERE slug = ?", (slug,))
        self._connection.commit()

    # -- Puzzles --

    def record_puzzle(
        self, puzzle_date: date, topic_slug: str, difficulty: str, solution: str,
        hints: Optional[list[str]] = None,
    ) -> None:
        self._connection.execute(
            "INSERT OR IGNORE INTO puzzles (date, topic_slug, difficulty, solution, hints) "
            "VALUES (?, ?, ?, ?, ?)",
            (puzzle_date.isoformat(), topic_slug, difficulty, solution,
             json.dumps(hints or [])),
        )
        self._connection.commit()

    def update_puzzle_hints(
        self, puzzle_date: date, topic_slug: str, difficulty: str, hints: list[str],
    ) -> None:
        self._connection.execute(
            "UPDATE puzzles SET hints = ? "
            "WHERE date = ? AND topic_slug = ? AND difficulty = ?",
            (json.dumps(hints), puzzle_date.isoformat(), topic_slug, difficulty),
        )
        self._connection.commit()

    def get_puzzle_solution(
        self, puzzle_date: date, topic_slug: str, difficulty: str
    ) -> Optional[str]:
        row = self._connection.execute(
            "SELECT solution FROM puzzles WHERE date = ? AND topic_slug = ? AND difficulty = ?",
            (puzzle_date.isoformat(), topic_slug, difficulty),
        ).fetchone()
        if row is None:
            return None
        return row["solution"]

    def get_puzzle_hints(
        self, puzzle_date: date, topic_slug: str, difficulty: str
    ) -> list[str]:
        row = self._connection.execute(
            "SELECT hints FROM puzzles WHERE date = ? AND topic_slug = ? AND difficulty = ?",
            (puzzle_date.isoformat(), topic_slug, difficulty),
        ).fetchone()
        if row is None:
            return []
        return json.loads(row["hints"])

    # -- Puzzle Pool --

    def draw_puzzle(
        self, puzzle_date: date, topic_slug: str, difficulty: str,
    ) -> Optional[str]:
        """Draw a random pooled solution and record it as that date's puzzle.

        Both happen in one transaction, so a solution is never lost between
        leaving the pool and becoming a puzzle. Hints are added afterwards.
        Returns the solution, or None if the pool is empty.
        """
        with self._connection:
            row = self._connection.execute(
                "SELECT pool_id, solution FROM pool_solutions "
                "WHERE topic_slug = ? AND difficulty = ? ORDER BY RANDOM() LIMIT 1",
                (topic_slug, difficulty),
            ).fetchone()
            if row is None:
                return None
            self._connection.execute("DELETE FROM pool_solutions WHERE pool_id = ?", (row["pool_id"],))
            self._connection.execute(
                "INSERT INTO puzzles (date, topic_slug, difficulty, solution, hints) "
                "VALUES (?, ?, ?, ?, '[]')",
                (puzzle_date.isoformat(), topic_slug, difficulty, row["solution"]),
            )
        return row["solution"]

    def trim_pool(self, topic_slug: str, difficulty: str, keep: int) -> int:
        """Drop all but the first `keep` pooled solutions of a series. Returns count dropped."""
        cursor = self._connection.execute(
            "DELETE FROM pool_solutions WHERE topic_slug = ? AND difficulty = ? AND pool_id NOT IN ("
            "  SELECT pool_id FROM pool_solutions WHERE topic_slug = ? AND difficulty = ? "
            "  ORDER BY pool_id LIMIT ?)",
            (topic_slug, difficulty, topic_slug, difficulty, keep),
        )
        self._connection.commit()
        return cursor.rowcount

    def delete_unplayed_puzzle(self, puzzle_date: date, topic_slug: str, difficulty: str) -> bool:
        """Delete a puzzle nobody has played. Returns whether one was deleted."""
        cursor = self._connection.execute(
            "DELETE FROM puzzles WHERE date = ? AND topic_slug = ? AND difficulty = ? "
            "AND NOT EXISTS (SELECT 1 FROM games g WHERE g.date = puzzles.date "
            "  AND g.topic_slug = puzzles.topic_slug AND g.difficulty = puzzles.difficulty)",
            (puzzle_date.isoformat(), topic_slug, difficulty),
        )
        self._connection.commit()
        return cursor.rowcount == 1

    def get_pool_solutions(self, topic_slug: str, difficulty: str) -> list[str]:
        rows = self._connection.execute(
            "SELECT solution FROM pool_solutions WHERE topic_slug = ? AND difficulty = ? "
            "ORDER BY pool_id",
            (topic_slug, difficulty),
        ).fetchall()
        return [row["solution"] for row in rows]

    def set_preview_solutions(self, topic_slug: str, solutions: list[str]) -> None:
        """Move solutions out of the topic's pools into its preview.

        Preview solutions are never drawn as puzzles and stay excluded from
        future batches, like used solutions.
        """
        with self._connection:
            self._connection.execute("DELETE FROM preview_solutions WHERE topic_slug = ?", (topic_slug,))
            for position, solution in enumerate(solutions):
                self._connection.execute(
                    "DELETE FROM pool_solutions WHERE topic_slug = ? AND solution = ?",
                    (topic_slug, solution),
                )
                self._connection.execute(
                    "INSERT INTO preview_solutions (topic_slug, position, solution) VALUES (?, ?, ?)",
                    (topic_slug, position, solution),
                )

    def get_preview_solutions(self, topic_slug: str) -> list[str]:
        rows = self._connection.execute(
            "SELECT solution FROM preview_solutions WHERE topic_slug = ? ORDER BY position",
            (topic_slug,),
        ).fetchall()
        return [row["solution"] for row in rows]

    # -- Series --

    def set_series_status(self, topic_slug: str, difficulty: str, status: str) -> None:
        """Set a series' status: available, winding_down, finished or unavailable."""
        self._connection.execute(
            "INSERT INTO series (topic_slug, difficulty, status) VALUES (?, ?, ?) "
            "ON CONFLICT (topic_slug, difficulty) DO UPDATE SET status = excluded.status",
            (topic_slug, difficulty, status),
        )
        self._connection.commit()

    def get_series_status(self, topic_slug: str, difficulty: str) -> Optional[str]:
        row = self._connection.execute(
            "SELECT status FROM series WHERE topic_slug = ? AND difficulty = ?",
            (topic_slug, difficulty),
        ).fetchone()
        return row["status"] if row is not None else None

    def set_series_attention(
        self, topic_slug: str, difficulty: str, detail: Optional[str],
    ) -> None:
        """Flag a series for the admin (or clear the flag with None)."""
        self._connection.execute(
            "UPDATE series SET needs_attention = ? WHERE topic_slug = ? AND difficulty = ?",
            (detail, topic_slug, difficulty),
        )
        self._connection.commit()

    def get_all_series(self) -> list[dict[str, Any]]:
        """Every series with its pool size and latest refill, for the control panel."""
        rows = self._connection.execute(
            "SELECT s.topic_slug, t.name AS topic_name, s.difficulty, s.status, s.needs_attention, "
            "(SELECT COUNT(*) FROM pool_solutions p "
            " WHERE p.topic_slug = s.topic_slug AND p.difficulty = s.difficulty) AS pool_size, "
            "(SELECT COUNT(*) FROM puzzles z "
            " WHERE z.topic_slug = s.topic_slug AND z.difficulty = s.difficulty) AS puzzles_played, "
            "(SELECT generated || '/' || kept || ' at ' || finished_at FROM pool_refills r "
            " WHERE r.topic_slug = s.topic_slug AND r.difficulty = s.difficulty "
            " ORDER BY refill_id DESC LIMIT 1) AS last_refill "
            "FROM series s JOIN topics t ON t.slug = s.topic_slug "
            "ORDER BY s.needs_attention IS NULL, t.name, s.difficulty"
        ).fetchall()
        return [dict(row) for row in rows]

    def _series_display_state(
        self, topic_slug: str, difficulty: str, status: str, today: date,
    ) -> dict[str, Any]:
        """How a series shows to players today.

        A finished series still offers today's puzzle if one was drawn, and
        a winding-down series reports how many puzzles remain.
        """
        remaining = self.pool_count(topic_slug, difficulty)
        has_puzzle_today = self.get_puzzle_solution(today, topic_slug, difficulty) is not None
        if status == "finished" and not has_puzzle_today:
            return {"state": "finished", "remaining": 0}
        if status in ("winding_down", "finished"):
            return {"state": "winding_down", "remaining": remaining}
        return {"state": "available", "remaining": remaining}

    def pool_count(self, topic_slug: str, difficulty: str) -> int:
        """Return the number of undrawn solutions in the pool."""
        row = self._connection.execute(
            "SELECT COUNT(*) AS cnt FROM pool_solutions "
            "WHERE topic_slug = ? AND difficulty = ?",
            (topic_slug, difficulty),
        ).fetchone()
        return row["cnt"]

    def get_all_known_solutions(self, topic_slug: str) -> list[str]:
        """Return all solutions (used, pooled and in the preview) for a topic, for dedup."""
        rows = self._connection.execute(
            "SELECT solution FROM puzzles WHERE topic_slug = ? "
            "UNION "
            "SELECT solution FROM pool_solutions WHERE topic_slug = ? "
            "UNION "
            "SELECT solution FROM preview_solutions WHERE topic_slug = ?",
            (topic_slug, topic_slug, topic_slug),
        ).fetchall()
        return [row["solution"] for row in rows]

    def insert_pool_solutions(
        self,
        topic_slug: str,
        difficulty: str,
        solutions: list[str],
    ) -> int:
        """Insert solutions into the pool, skipping duplicates. Returns count inserted."""
        generated_at = _utcnow_iso()
        before = self._connection.total_changes
        self._connection.executemany(
            "INSERT OR IGNORE INTO pool_solutions "
            "(topic_slug, difficulty, solution, generated_at) "
            "VALUES (?, ?, ?, ?)",
            [(topic_slug, difficulty, solution, generated_at) for solution in solutions],
        )
        self._connection.commit()
        return self._connection.total_changes - before

    def remove_cross_difficulty_pool_duplicates(self, topic_slug: str) -> int:
        """Drop non-normal pool solutions that also appear in the normal pool.

        Returns count deleted.
        """
        before = self._connection.total_changes
        self._connection.execute(
            "DELETE FROM pool_solutions "
            "WHERE topic_slug = ? AND difficulty != 'normal' AND solution IN ("
            "  SELECT solution FROM pool_solutions "
            "  WHERE topic_slug = ? AND difficulty = 'normal')",
            (topic_slug, topic_slug),
        )
        self._connection.commit()
        return self._connection.total_changes - before

    def record_pool_refill(
        self, topic_slug: str, difficulty: str, generated: int, kept: int,
    ) -> None:
        self._connection.execute(
            "INSERT INTO pool_refills (topic_slug, difficulty, generated, kept, finished_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (topic_slug, difficulty, generated, kept, _utcnow_iso()),
        )
        self._connection.commit()

    def get_last_pool_refill(
        self, topic_slug: str, difficulty: str,
    ) -> Optional[dict[str, Any]]:
        row = self._connection.execute(
            "SELECT generated, kept, finished_at FROM pool_refills "
            "WHERE topic_slug = ? AND difficulty = ? "
            "ORDER BY refill_id DESC LIMIT 1",
            (topic_slug, difficulty),
        ).fetchone()
        return dict(row) if row is not None else None

    # -- Games --

    def create_game(
        self, puzzle_date: date, topic_slug: str, difficulty: str,
        user_id: Optional[int] = None,
    ) -> dict[str, Any]:
        now = _utcnow_iso()
        share_code = secrets.token_hex(3).upper()
        cursor = self._connection.execute(
            "INSERT INTO games (date, topic_slug, difficulty, started_at, user_id, share_code) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (puzzle_date.isoformat(), topic_slug, difficulty, now, user_id, share_code),
        )
        self._connection.commit()
        assert cursor.lastrowid is not None
        return {"game_id": cursor.lastrowid, "share_code": share_code}

    def record_question(
        self,
        game_id: int,
        question_number: int,
        question: str,
        answer: str,
        explanation: str = "",
        user_id: Optional[int] = None,
    ) -> None:
        now = _utcnow_iso()
        self._connection.execute(
            """
            INSERT INTO questions
                (game_id, question_number, question, answer, explanation, asked_at, user_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (game_id, question_number, question, answer, explanation, now, user_id),
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

    def record_hint_reveal(
        self, game_id: int, hint_index: int, after_question: int,
    ) -> None:
        now = _utcnow_iso()
        self._connection.execute(
            "INSERT OR IGNORE INTO hint_reveals (game_id, hint_index, after_question, revealed_at) "
            "VALUES (?, ?, ?, ?)",
            (game_id, hint_index, after_question, now),
        )
        self._connection.commit()

    def get_game_history(self, game_id: int) -> list[dict[str, Any]]:
        """Fetch Q&A pairs for a game, ordered by question number."""
        rows = self._connection.execute(
            "SELECT question_number, question, answer "
            "FROM questions WHERE game_id = ? ORDER BY question_number",
            (game_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def get_hint_reveals(self, game_id: int) -> list[dict[str, Any]]:
        rows = self._connection.execute(
            "SELECT hint_index, after_question FROM hint_reveals "
            "WHERE game_id = ? ORDER BY hint_index",
            (game_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def get_game(self, game_id: int) -> Optional[dict[str, Any]]:
        row = self._connection.execute(
            "SELECT game_id, date, topic_slug, difficulty, started_at, ended_at, "
            "result, questions_asked, user_id, share_code FROM games WHERE game_id = ?",
            (game_id,),
        ).fetchone()
        if row is None:
            return None
        return dict(row)

    def get_existing_game(
        self, user_id: int, puzzle_date: date, topic_slug: str, difficulty: str,
    ) -> Optional[dict[str, Any]]:
        """Return the user's game for a given puzzle, if any."""
        row = self._connection.execute(
            "SELECT game_id, date, topic_slug, difficulty, started_at, "
            "ended_at, result, questions_asked, user_id, share_code "
            "FROM games "
            "WHERE user_id = ? AND date = ? AND topic_slug = ? "
            "AND difficulty = ? "
            "ORDER BY started_at DESC LIMIT 1",
            (user_id, puzzle_date.isoformat(), topic_slug, difficulty),
        ).fetchone()
        if row is None:
            return None
        game = dict(row)
        questions = self._connection.execute(
            "SELECT question_number, question, answer, explanation "
            "FROM questions WHERE game_id = ? ORDER BY question_number",
            (game["game_id"],),
        ).fetchall()
        game["questions"] = [dict(question) for question in questions]
        hint_reveals = self.get_hint_reveals(game["game_id"])
        game["hint_reveals"] = hint_reveals
        if game["ended_at"] is not None:
            solution = self.get_puzzle_solution(
                puzzle_date, topic_slug, difficulty,
            )
            hints = self.get_puzzle_hints(puzzle_date, topic_slug, difficulty)
            game["solution"] = solution
            game["hints"] = hints
        elif hint_reveals:
            # Include revealed hint texts so in-progress games can restore them.
            all_hints = self.get_puzzle_hints(puzzle_date, topic_slug, difficulty)
            revealed_hints = {}
            for reveal in hint_reveals:
                index = reveal["hint_index"]
                if index < len(all_hints):
                    revealed_hints[index] = all_hints[index]
            game["revealed_hints"] = revealed_hints
        return game

    def has_played_puzzle(
        self, user_id: int, puzzle_date: date, topic_slug: str, difficulty: str,
    ) -> bool:
        """Check whether a user has completed a game for the given puzzle."""
        row = self._connection.execute(
            "SELECT 1 FROM games "
            "WHERE user_id = ? AND date = ? AND topic_slug = ? AND difficulty = ? "
            "AND result IS NOT NULL "
            "LIMIT 1",
            (user_id, puzzle_date.isoformat(), topic_slug, difficulty),
        ).fetchone()
        return row is not None

    def get_game_statuses(
        self, user_id: int, puzzle_date: date,
    ) -> list[dict[str, Any]]:
        """Return summary status of all games for a user on a given date."""
        rows = self._connection.execute(
            "SELECT topic_slug, difficulty, result, questions_asked "
            "FROM games "
            "WHERE user_id = ? AND date = ? "
            "AND (result IS NOT NULL OR questions_asked > 0) "
            "ORDER BY started_at DESC",
            (user_id, puzzle_date.isoformat()),
        ).fetchall()
        return [dict(row) for row in rows]

    def get_game_by_share_code(self, share_code: str) -> Optional[dict[str, Any]]:
        """Return a game by its share code, for replay."""
        row = self._connection.execute(
            "SELECT g.game_id, g.user_id, g.date, g.topic_slug, g.difficulty, "
            "g.started_at, g.ended_at, g.result, g.questions_asked, "
            "g.share_code, a.username, a.display_name "
            "FROM games g "
            "JOIN accounts a ON a.user_id = g.user_id "
            "WHERE g.share_code = ? "
            "LIMIT 1",
            (share_code,),
        ).fetchone()
        if row is None:
            return None
        game = dict(row)
        questions = self._connection.execute(
            "SELECT question_number, question, answer, explanation "
            "FROM questions WHERE game_id = ? ORDER BY question_number",
            (game["game_id"],),
        ).fetchall()
        game["questions"] = [dict(question) for question in questions]
        game["hint_reveals"] = self.get_hint_reveals(game["game_id"])
        topic_name = self.get_topic_name(game["topic_slug"])
        game["topic_name"] = topic_name
        # The answer is revealed once the game ends, or once its day is over
        # for games left unfinished.
        puzzle_date = date.fromisoformat(game["date"])
        if game["ended_at"] is not None or puzzle_date < date.today():
            game["solution"] = self.get_puzzle_solution(
                puzzle_date, game["topic_slug"], game["difficulty"],
            )
            game["hints"] = self.get_puzzle_hints(
                puzzle_date, game["topic_slug"], game["difficulty"],
            )
        return game

    def get_history(self, user_id: Optional[int] = None) -> list[dict[str, Any]]:
        if user_id is not None:
            games = self._connection.execute(
                """
                SELECT g.game_id, g.date, g.topic_slug, t.name AS topic_name,
                       g.difficulty, dp.solution, g.started_at, g.ended_at,
                       g.result, g.questions_asked, g.share_code
                FROM games g
                JOIN puzzles dp
                    ON g.date = dp.date
                    AND g.topic_slug = dp.topic_slug
                    AND g.difficulty = dp.difficulty
                LEFT JOIN topics t ON g.topic_slug = t.slug
                WHERE g.user_id = ?
                AND (g.result IS NOT NULL OR g.questions_asked > 0)
                ORDER BY g.started_at DESC
                """,
                (user_id,),
            ).fetchall()
        else:
            games = self._connection.execute(
                """
                SELECT g.game_id, g.date, g.topic_slug, t.name AS topic_name,
                       g.difficulty, dp.solution, g.started_at, g.ended_at,
                       g.result, g.questions_asked, g.share_code
                FROM games g
                JOIN puzzles dp
                    ON g.date = dp.date
                    AND g.topic_slug = dp.topic_slug
                    AND g.difficulty = dp.difficulty
                LEFT JOIN topics t ON g.topic_slug = t.slug
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
                "topic_name": game["topic_name"] or game["topic_slug"],
                "difficulty": game["difficulty"],
                "solution": game["solution"],
                "share_code": game["share_code"],
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
        *, daily_question_limit: int, daily_topic_limit: int,
        monthly_avatar_limit: int = 3,
    ) -> int:
        now = _utcnow_iso()
        password_hash = self._hash_password(password)
        player_code = self._generate_player_code()
        cursor = self._connection.execute(
            "INSERT INTO accounts (username, password_hash, role, invite_code, "
            "daily_question_limit, daily_topic_limit, monthly_avatar_limit, "
            "player_code, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (username, password_hash, role, invite_code,
             daily_question_limit, daily_topic_limit, monthly_avatar_limit,
             player_code, now),
        )
        self._connection.commit()
        assert cursor.lastrowid is not None
        return cursor.lastrowid

    def get_account_by_username(self, username: str) -> Optional[dict[str, Any]]:
        row = self._connection.execute(
            "SELECT user_id, username, password_hash, role, blocked, "
            "player_code, created_at "
            "FROM accounts WHERE username = ?",
            (username,),
        ).fetchone()
        if row is None:
            return None
        return dict(row)

    def get_account_by_id(self, user_id: int) -> Optional[dict[str, Any]]:
        row = self._connection.execute(
            "SELECT user_id, username, role, blocked, "
            "daily_question_limit, daily_topic_limit, invite_code, "
            "display_name, player_code, anonymous, "
            "avatar_version, avatar_generations_used, "
            "avatar_generation_reset, monthly_avatar_limit, created_at "
            "FROM accounts WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        if row is None:
            return None
        return dict(row)

    def get_all_accounts(self) -> list[dict[str, Any]]:
        rows = self._connection.execute(
            "SELECT user_id, username, role, blocked, "
            "daily_question_limit, daily_topic_limit, invite_code, "
            "display_name, player_code, anonymous, "
            "avatar_version, monthly_avatar_limit, created_at "
            "FROM accounts ORDER BY created_at DESC"
        ).fetchall()
        return [dict(row) for row in rows]

    def update_account_limits(
        self, user_id: int,
        daily_question_limit: Optional[int] = None,
        daily_topic_limit: Optional[int] = None,
        monthly_avatar_limit: Optional[int] = None,
    ) -> bool:
        updates = []
        params: list[Any] = []
        if daily_question_limit is not None:
            updates.append("daily_question_limit = ?")
            params.append(daily_question_limit)
        if daily_topic_limit is not None:
            updates.append("daily_topic_limit = ?")
            params.append(daily_topic_limit)
        if monthly_avatar_limit is not None:
            updates.append("monthly_avatar_limit = ?")
            params.append(monthly_avatar_limit)
        if not updates:
            return True
        params.append(user_id)
        cursor = self._connection.execute(
            f"UPDATE accounts SET {', '.join(updates)} WHERE user_id = ?",
            params,
        )
        self._connection.commit()
        return cursor.rowcount > 0

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

    # -- Profiles & Friends --

    def update_profile(
        self, user_id: int, display_name: Optional[str], anonymous: bool,
    ) -> bool:
        """Update display_name and anonymous flag. Returns True if the row was updated."""
        cursor = self._connection.execute(
            "UPDATE accounts SET display_name = ?, anonymous = ? WHERE user_id = ?",
            (display_name, 1 if anonymous else 0, user_id),
        )
        self._connection.commit()
        return cursor.rowcount > 0

    def get_avatar_usage(self, user_id: int, today: date) -> dict[str, Any]:
        """Return avatar generation usage, resetting the counter if a new month started."""
        row = self._connection.execute(
            "SELECT avatar_generations_used, avatar_generation_reset, monthly_avatar_limit "
            "FROM accounts WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        if row is None:
            return {"used": 0, "limit": 3}
        reset_date_str = row["avatar_generation_reset"]
        used = row["avatar_generations_used"]
        if reset_date_str is not None:
            reset_date = date.fromisoformat(reset_date_str)
            # Reset if we're in a different month.
            if today.year != reset_date.year or today.month != reset_date.month:
                self._connection.execute(
                    "UPDATE accounts SET avatar_generations_used = 0, "
                    "avatar_generation_reset = ? WHERE user_id = ?",
                    (today.isoformat(), user_id),
                )
                self._connection.commit()
                used = 0
        return {"used": used, "limit": row["monthly_avatar_limit"]}

    def increment_avatar_generation(self, user_id: int, today: date) -> None:
        """Increment the avatar generation counter and set the reset date if unset."""
        self._connection.execute(
            "UPDATE accounts SET avatar_generations_used = avatar_generations_used + 1, "
            "avatar_generation_reset = COALESCE(avatar_generation_reset, ?) "
            "WHERE user_id = ?",
            (today.isoformat(), user_id),
        )
        self._connection.commit()

    def bump_avatar_version(self, user_id: int) -> int:
        """Increment avatar_version and return the new value."""
        self._connection.execute(
            "UPDATE accounts SET avatar_version = avatar_version + 1 WHERE user_id = ?",
            (user_id,),
        )
        self._connection.commit()
        row = self._connection.execute(
            "SELECT avatar_version FROM accounts WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        return row["avatar_version"] if row else 0

    def get_accounts_without_avatars(self) -> list[dict[str, Any]]:
        """Return accounts with avatar_version = 0 (no avatar generated yet)."""
        rows = self._connection.execute(
            "SELECT user_id, username, player_code "
            "FROM accounts WHERE avatar_version = 0 AND player_code IS NOT NULL"
        ).fetchall()
        return [dict(row) for row in rows]

    def get_account_by_player_code(self, player_code: str) -> Optional[dict[str, Any]]:
        """Look up an account by player_code. Returns None if not found."""
        row = self._connection.execute(
            "SELECT user_id, username, display_name, player_code, anonymous "
            "FROM accounts WHERE player_code = ?",
            (player_code,),
        ).fetchone()
        if row is None:
            return None
        return dict(row)

    def search_players(self, query: str, exclude_user_id: int) -> list[dict[str, Any]]:
        """Search non-anonymous accounts by username or display_name (LIKE match),
        or by exact player code. Excludes the searching user and anonymous
        players. Returns up to 20 results."""
        pattern = f"%{query}%"
        rows = self._connection.execute(
            "SELECT user_id, username, display_name, player_code, avatar_version "
            "FROM accounts "
            "WHERE anonymous = 0 AND user_id != ? "
            "AND (username LIKE ? OR display_name LIKE ? OR player_code = ?) "
            "LIMIT 20",
            (exclude_user_id, pattern, pattern, query.strip().upper()),
        ).fetchall()
        return [dict(row) for row in rows]

    def add_friend(self, user_id: int, friend_id: int) -> bool:
        """Add a follow relationship. Returns True if created, False if already exists."""
        if user_id == friend_id:
            return False
        now = _utcnow_iso()
        try:
            self._connection.execute(
                "INSERT INTO friends (user_id, friend_id, created_at) VALUES (?, ?, ?)",
                (user_id, friend_id, now),
            )
            self._connection.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def remove_friend(self, user_id: int, friend_id: int) -> bool:
        """Remove a follow relationship. Returns True if a row was deleted."""
        cursor = self._connection.execute(
            "DELETE FROM friends WHERE user_id = ? AND friend_id = ?",
            (user_id, friend_id),
        )
        self._connection.commit()
        return cursor.rowcount > 0

    def get_friends(self, user_id: int) -> list[dict[str, Any]]:
        """Return all friends (accounts the user follows). Does NOT filter by
        anonymous — the API layer gates access."""
        rows = self._connection.execute(
            "SELECT a.user_id, a.username, a.display_name, a.player_code, "
            "a.avatar_version, a.anonymous "
            "FROM friends f "
            "JOIN accounts a ON a.user_id = f.friend_id "
            "WHERE f.user_id = ? "
            "ORDER BY f.created_at",
            (user_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    # -- Recent results --

    def get_recent_results(self, user_id: int, limit: int = 3) -> list[dict[str, Any]]:
        """Get the user's most recent solved games that a friend also solved.

        Returns up to `limit` games, each with the user's own result and ALL
        friends who also solved the same puzzle. Unsolved games, failed or
        unfinished, are never shown to others. The API layer handles friend
        selection/filtering.

        Returns empty list if the user is anonymous.
        """
        # Check if user is anonymous.
        account = self._connection.execute(
            "SELECT anonymous FROM accounts WHERE user_id = ?", (user_id,)
        ).fetchone()
        if account is None or account["anonymous"]:
            return []

        # Find the user's most recent wins where at least one non-anonymous
        # friend also won the same puzzle.
        user_games = self._connection.execute(
            "SELECT g.game_id, g.topic_slug, t.name AS topic_name, "
            "g.difficulty, g.date, g.questions_asked "
            "FROM games g "
            "LEFT JOIN topics t ON g.topic_slug = t.slug "
            "WHERE g.user_id = ? AND g.result = 'win' "
            "AND EXISTS ("
            "  SELECT 1 FROM friends f "
            "  JOIN games fg ON fg.user_id = f.friend_id "
            "    AND fg.date = g.date "
            "    AND fg.topic_slug = g.topic_slug "
            "    AND fg.difficulty = g.difficulty "
            "    AND fg.result = 'win' "
            "  JOIN accounts fa ON fa.user_id = f.friend_id "
            "  WHERE f.user_id = ? AND fa.anonymous = 0"
            ") "
            "ORDER BY g.ended_at DESC "
            "LIMIT ?",
            (user_id, user_id, limit),
        ).fetchall()

        if not user_games:
            return []

        results = []
        for game_row in user_games:
            game = dict(game_row)
            game["topic_name"] = game["topic_name"] or game["topic_slug"]

            # Count hints for this game.
            hint_count = self._connection.execute(
                "SELECT COUNT(*) AS cnt FROM hint_reveals WHERE game_id = ?",
                (game["game_id"],),
            ).fetchone()["cnt"]
            game["hints_used"] = hint_count

            # Get friends' won games on the same puzzle.
            friend_games = self._connection.execute(
                "SELECT a.display_name, a.username, a.player_code, "
                "a.avatar_version, g.questions_asked, "
                "(SELECT COUNT(*) FROM hint_reveals h "
                " WHERE h.game_id = g.game_id) AS hints_used "
                "FROM friends f "
                "JOIN accounts a ON f.friend_id = a.user_id "
                "JOIN games g ON g.user_id = a.user_id "
                "  AND g.date = ? "
                "  AND g.topic_slug = ? "
                "  AND g.difficulty = ? "
                "  AND g.result = 'win' "
                "WHERE f.user_id = ? AND a.anonymous = 0",
                (game["date"], game["topic_slug"],
                 game["difficulty"], user_id),
            ).fetchall()

            game["friends"] = [dict(friend) for friend in friend_games]
            results.append(game)

        return results

    def get_puzzle_winners(
        self, puzzle_date: date, topic_slug: str, difficulty: str,
        requesting_user_id: int,
    ) -> list[dict[str, Any]]:
        """Return all non-anonymous accounts that won a specific puzzle.

        Each row includes is_friend (whether the requesting user follows them).
        Scoring and sorting are left to the caller.
        """
        rows = self._connection.execute(
            "SELECT a.user_id, a.username, a.display_name, "
            "a.player_code, a.avatar_version, "
            "g.questions_asked, g.share_code, "
            "(SELECT COUNT(*) FROM hint_reveals h "
            " WHERE h.game_id = g.game_id) AS hints_used, "
            "CASE WHEN f.friend_id IS NOT NULL THEN 1 ELSE 0 END AS is_friend "
            "FROM games g "
            "JOIN accounts a ON g.user_id = a.user_id "
            "LEFT JOIN friends f ON f.user_id = ? AND f.friend_id = a.user_id "
            "WHERE g.date = ? AND g.topic_slug = ? AND g.difficulty = ? "
            "AND g.result = 'win' AND a.anonymous = 0",
            (requesting_user_id, puzzle_date.isoformat(), topic_slug, difficulty),
        ).fetchall()
        return [dict(row) for row in rows]

    # -- Friend suggestions --

    def get_friend_suggestions(self, user_id: int) -> list[dict[str, Any]]:
        """Return the full candidate pool of users to suggest as friends.

        Three tiers (priority order):
        1. Users who follow you but you don't follow back
        2. 2nd-order connections (friends-of-friends), excluding tier 1
        3. Users who registered with the same invite code, excluding tiers 1-2

        Returns empty list if the user is anonymous.  Each dict includes:
        user_id, username, display_name, player_code, avatar_version, tier, reason.
        """
        account = self._connection.execute(
            "SELECT anonymous, invite_code FROM accounts WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        if account is None or account["anonymous"]:
            return []

        seen_ids: set[int] = set()
        pool: list[dict[str, Any]] = []

        # Tier 1: users who follow me but I don't follow back.
        tier1_rows = self._connection.execute(
            "SELECT a.user_id, a.username, a.display_name, a.player_code, "
            "a.avatar_version "
            "FROM friends f "
            "JOIN accounts a ON a.user_id = f.user_id "
            "WHERE f.friend_id = ? "
            "  AND a.anonymous = 0 "
            "  AND f.user_id NOT IN ("
            "    SELECT friend_id FROM friends WHERE user_id = ?"
            "  ) "
            "ORDER BY a.user_id",
            (user_id, user_id),
        ).fetchall()
        for row in tier1_rows:
            seen_ids.add(row["user_id"])
            pool.append({
                **dict(row),
                "tier": 1,
                "reason": "Follows you",
            })

        # Tier 2: people my friends follow (friends-of-friends).
        tier2_rows = self._connection.execute(
            "SELECT a.user_id, a.username, a.display_name, "
            "a.player_code, a.avatar_version, "
            "COALESCE(connector.display_name, connector.username) "
            "  AS connector_name "
            "FROM friends my_follows "
            "JOIN friends fof ON fof.user_id = my_follows.friend_id "
            "JOIN accounts a ON a.user_id = fof.friend_id "
            "JOIN accounts connector ON connector.user_id = my_follows.friend_id "
            "WHERE my_follows.user_id = ? "
            "  AND a.anonymous = 0 "
            "  AND a.user_id != ? "
            "  AND a.user_id NOT IN ("
            "    SELECT friend_id FROM friends WHERE user_id = ?"
            "  ) "
            "GROUP BY a.user_id "
            "ORDER BY a.user_id",
            (user_id, user_id, user_id),
        ).fetchall()
        for row in tier2_rows:
            if row["user_id"] in seen_ids:
                continue
            seen_ids.add(row["user_id"])
            connector_name = row["connector_name"] or "a friend"
            pool.append({
                "user_id": row["user_id"],
                "username": row["username"],
                "display_name": row["display_name"],
                "player_code": row["player_code"],
                "avatar_version": row["avatar_version"],
                "tier": 2,
                "reason": f"Friends with {connector_name}",
            })

        # Tier 3: same invite code.
        invite_code = account["invite_code"]
        if invite_code:
            tier3_rows = self._connection.execute(
                "SELECT a.user_id, a.username, a.display_name, a.player_code, "
                "a.avatar_version "
                "FROM accounts a "
                "WHERE a.invite_code = ? "
                "  AND a.user_id != ? "
                "  AND a.anonymous = 0 "
                "  AND a.user_id NOT IN ("
                "    SELECT friend_id FROM friends WHERE user_id = ?"
                "  ) "
                "ORDER BY a.user_id",
                (invite_code, user_id, user_id),
            ).fetchall()
            for row in tier3_rows:
                if row["user_id"] in seen_ids:
                    continue
                seen_ids.add(row["user_id"])
                pool.append({
                    **dict(row),
                    "tier": 3,
                    "reason": "Joined from the same invite",
                })

        return pool


    # -- Activity log --

    def log_activity(
        self, user_id: int, action: str, detail: Optional[dict[str, Any]] = None,
    ) -> None:
        now = _utcnow_iso()
        self._connection.execute(
            "INSERT INTO activity_log (user_id, action, detail, created_at) "
            "VALUES (?, ?, ?, ?)",
            (user_id, action, json.dumps(detail) if detail else None, now),
        )
        self._connection.commit()

    def get_activity_log(
        self, limit: int = 50, offset: int = 0,
    ) -> list[dict[str, Any]]:
        rows = self._connection.execute(
            "SELECT al.log_id, al.user_id, a.username, al.action, "
            "al.detail, al.created_at "
            "FROM activity_log al "
            "JOIN accounts a ON a.user_id = al.user_id "
            "ORDER BY al.created_at DESC, al.log_id DESC "
            "LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
        return [dict(row) for row in rows]

    # -- Invites --

    def create_invite(
        self, alias: Optional[str] = None, uses: int = 1, role: str = "user",
        daily_question_limit: Optional[int] = None,
        daily_topic_limit: Optional[int] = None,
        monthly_avatar_limit: Optional[int] = None,
    ) -> str:
        code = secrets.token_hex(4).upper()
        now = _utcnow_iso()
        self._connection.execute(
            "INSERT INTO invites (code, alias, role, remaining_uses, "
            "daily_question_limit, daily_topic_limit, monthly_avatar_limit, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (code, alias, role, uses, daily_question_limit, daily_topic_limit,
             monthly_avatar_limit, now),
        )
        self._connection.commit()
        return code

    def get_invite(self, code: str) -> Optional[dict[str, Any]]:
        row = self._connection.execute(
            "SELECT code, alias, role, remaining_uses, "
            "daily_question_limit, daily_topic_limit, "
            "monthly_avatar_limit, created_at "
            "FROM invites WHERE code = ?",
            (code,),
        ).fetchone()
        if row is None:
            return None
        return dict(row)

    def get_all_invites(self) -> list[dict[str, Any]]:
        rows = self._connection.execute(
            "SELECT code, alias, role, remaining_uses, "
            "daily_question_limit, daily_topic_limit, "
            "monthly_avatar_limit, created_at "
            "FROM invites ORDER BY created_at DESC"
        ).fetchall()
        return [dict(row) for row in rows]

    def consume_invite(self, code: str) -> Optional[dict[str, Any]]:
        """Decrement remaining uses. Returns invite details if valid, else None."""
        row = self._connection.execute(
            "SELECT remaining_uses, role, daily_question_limit, daily_topic_limit, "
            "monthly_avatar_limit "
            "FROM invites WHERE code = ?", (code,)
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
        return {
            "role": row["role"],
            "daily_question_limit": row["daily_question_limit"],
            "daily_topic_limit": row["daily_topic_limit"],
            "monthly_avatar_limit": row["monthly_avatar_limit"],
        }

    def delete_invite(self, code: str) -> bool:
        cursor = self._connection.execute(
            "DELETE FROM invites WHERE code = ?", (code,),
        )
        self._connection.commit()
        return cursor.rowcount > 0

    # -- Daily usage --

    def get_daily_usage(self, user_id: int, usage_date: date) -> dict[str, int]:
        row = self._connection.execute(
            "SELECT questions_used, topic_suggestions_used FROM daily_usage "
            "WHERE user_id = ? AND date = ?",
            (user_id, usage_date.isoformat()),
        ).fetchone()
        if row is None:
            return {"questions_used": 0, "topic_suggestions_used": 0}
        return dict(row)

    def increment_daily_questions(self, user_id: int, usage_date: date) -> None:
        self._connection.execute(
            "INSERT INTO daily_usage (user_id, date, questions_used) VALUES (?, ?, 1) "
            "ON CONFLICT(user_id, date) DO UPDATE SET questions_used = questions_used + 1",
            (user_id, usage_date.isoformat()),
        )
        self._connection.commit()

    def increment_daily_topic_suggestions(self, user_id: int, usage_date: date) -> None:
        self._connection.execute(
            "INSERT INTO daily_usage (user_id, date, topic_suggestions_used) VALUES (?, ?, 1) "
            "ON CONFLICT(user_id, date) DO UPDATE SET topic_suggestions_used = topic_suggestions_used + 1",
            (user_id, usage_date.isoformat()),
        )
        self._connection.commit()

    def reset_daily_usage(self, user_id: int, usage_date: date) -> None:
        self._connection.execute(
            "DELETE FROM daily_usage WHERE user_id = ? AND date = ?",
            (user_id, usage_date.isoformat()),
        )
        self._connection.execute(
            "UPDATE accounts SET avatar_generations_used = 0 WHERE user_id = ?",
            (user_id,),
        )
        self._connection.commit()

    # -- Invite requests --

    def get_latest_invite_request_time(self) -> Optional[str]:
        """Return the created_at of the most recent invite request, or None."""
        row = self._connection.execute(
            "SELECT created_at FROM invite_requests ORDER BY request_id DESC LIMIT 1"
        ).fetchone()
        if row is None:
            return None
        return row["created_at"]

    def create_invite_request(self, contact_info: str) -> int:
        now = _utcnow_iso()
        cursor = self._connection.execute(
            "INSERT INTO invite_requests (contact_info, created_at) VALUES (?, ?)",
            (contact_info, now),
        )
        self._connection.commit()
        assert cursor.lastrowid is not None
        return cursor.lastrowid

    def get_all_invite_requests(self) -> list[dict[str, Any]]:
        rows = self._connection.execute(
            "SELECT request_id, contact_info, created_at "
            "FROM invite_requests ORDER BY created_at DESC"
        ).fetchall()
        return [dict(row) for row in rows]

    def delete_invite_request(self, request_id: int) -> bool:
        cursor = self._connection.execute(
            "DELETE FROM invite_requests WHERE request_id = ?", (request_id,),
        )
        self._connection.commit()
        return cursor.rowcount > 0

    # -- Query --

    def execute_readonly_query(self, sql: str) -> dict[str, Any]:
        """Execute a read-only SQL query and return columns + rows."""
        cursor = self._connection.execute(sql)
        columns = [desc[0] for desc in cursor.description] if cursor.description else []
        rows = [list(row) for row in cursor.fetchall()]
        return {"columns": columns, "rows": rows}

    def close(self) -> None:
        self._connection.close()


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
