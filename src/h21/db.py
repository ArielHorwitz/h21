from __future__ import annotations

import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Optional


class GameDatabase:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._connection = sqlite3.connect(db_path)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute("PRAGMA foreign_keys=ON")

    def ensure_schema(self) -> None:
        self._connection.executescript("""
            CREATE TABLE IF NOT EXISTS daily_puzzles (
                date     TEXT PRIMARY KEY,
                solution TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS games (
                game_id         INTEGER PRIMARY KEY AUTOINCREMENT,
                date            TEXT NOT NULL,
                started_at      TEXT NOT NULL,
                ended_at        TEXT,
                result          TEXT,
                questions_asked INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY (date) REFERENCES daily_puzzles(date)
            );

            CREATE TABLE IF NOT EXISTS questions (
                question_id     INTEGER PRIMARY KEY AUTOINCREMENT,
                game_id         INTEGER NOT NULL,
                question_number INTEGER NOT NULL,
                question        TEXT NOT NULL,
                answer          TEXT NOT NULL,
                asked_at        TEXT NOT NULL,
                FOREIGN KEY (game_id) REFERENCES games(game_id)
            );
        """)

    def record_puzzle(self, puzzle_date: date, solution: str) -> None:
        self._connection.execute(
            "INSERT OR IGNORE INTO daily_puzzles (date, solution) VALUES (?, ?)",
            (puzzle_date.isoformat(), solution),
        )
        self._connection.commit()

    def create_game(self, puzzle_date: date) -> int:
        now = _utcnow_iso()
        cursor = self._connection.execute(
            "INSERT INTO games (date, started_at) VALUES (?, ?)",
            (puzzle_date.isoformat(), now),
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
    ) -> None:
        now = _utcnow_iso()
        self._connection.execute(
            """
            INSERT INTO questions (game_id, question_number, question, answer, asked_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (game_id, question_number, question, answer, now),
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

    def get_history(self) -> list[dict[str, Any]]:
        games = self._connection.execute(
            """
            SELECT g.game_id, g.date, dp.solution, g.started_at, g.ended_at,
                   g.result, g.questions_asked
            FROM games g
            JOIN daily_puzzles dp ON g.date = dp.date
            ORDER BY g.started_at DESC
            """
        ).fetchall()

        result = []
        for game in games:
            questions = self._connection.execute(
                """
                SELECT question_number, question, answer, asked_at
                FROM questions
                WHERE game_id = ?
                ORDER BY question_number
                """,
                (game["game_id"],),
            ).fetchall()

            result.append({
                "game_id": game["game_id"],
                "date": game["date"],
                "solution": game["solution"],
                "started_at": game["started_at"],
                "ended_at": game["ended_at"],
                "result": game["result"],
                "questions_asked": game["questions_asked"],
                "questions": [dict(question) for question in questions],
            })

        return result

    def get_game(self, game_id: int) -> Optional[dict[str, Any]]:
        row = self._connection.execute(
            "SELECT game_id, date, started_at, ended_at, result, questions_asked "
            "FROM games WHERE game_id = ?",
            (game_id,),
        ).fetchone()
        if row is None:
            return None
        return dict(row)

    def close(self) -> None:
        self._connection.close()


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
