from __future__ import annotations

import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from h21.db import GameDatabase
from h21.sandbox import DEV_USERNAME, seed_database


class SandboxSeedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary_directory = tempfile.TemporaryDirectory()
        cls.today = date(2026, 8, 28)
        cls.friend_count = 3
        cls.history_days = 5
        db_path = Path(cls.temporary_directory.name).joinpath("h21.db")
        cls.summary = seed_database(
            db_path,
            password="test-password",
            friend_count=cls.friend_count,
            history_days=cls.history_days,
            rng_seed=21,
            today=cls.today,
        )
        cls.database = GameDatabase(db_path)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.database.close()
        cls.temporary_directory.cleanup()

    def test_dev_account_exists_and_authenticates(self) -> None:
        account = self.database.get_account_by_username(DEV_USERNAME)
        self.assertIsNotNone(account)
        self.assertEqual(account["role"], "dev")
        self.assertEqual(
            self.database.authenticate(DEV_USERNAME, "test-password"),
            self.summary["dev_user_id"],
        )

    def test_topics_are_ready_with_pooled_puzzles(self) -> None:
        self.assertGreater(self.summary["pooled_count"], 0)
        for topic_slug in self.summary["topic_slugs"]:
            self.assertEqual(self.database.get_topic(topic_slug)["status"], "ready")
            for difficulty in ("normal", "expert"):
                self.assertGreater(self.database.pool_count(topic_slug, difficulty), 0)

    def test_friend_connections_are_mutual(self) -> None:
        dev_id = self.summary["dev_user_id"]
        friends = self.database.get_friends(dev_id)
        friend_usernames = {friend["username"] for friend in friends}
        expected = set(self.summary["friend_usernames"])
        expected.add(self.summary["anonymous_username"])
        self.assertEqual(friend_usernames, expected)
        for friend in friends:
            followed_back = {
                entry["user_id"]
                for entry in self.database.get_friends(friend["user_id"])
            }
            self.assertIn(dev_id, followed_back)

    def test_friend_suggestions_cover_follower_and_friend_of_friend(self) -> None:
        suggestions = self.database.get_friend_suggestions(self.summary["dev_user_id"])
        suggested = {entry["username"]: entry["tier"] for entry in suggestions}
        self.assertEqual(suggested.get(self.summary["follower_username"]), 1)
        self.assertEqual(suggested.get(self.summary["friend_of_friend_username"]), 2)

    def test_every_game_has_a_matching_puzzle(self) -> None:
        orphans = self.database.execute_readonly_query(
            "SELECT COUNT(*) FROM games g "
            "LEFT JOIN daily_puzzles dp ON dp.date = g.date "
            "AND dp.topic_slug = g.topic_slug AND dp.difficulty = g.difficulty "
            "WHERE dp.date IS NULL"
        )
        self.assertEqual(orphans["rows"][0][0], 0)

    def test_game_timestamps_match_game_dates(self) -> None:
        mismatched = self.database.execute_readonly_query(
            "SELECT COUNT(*) FROM games "
            "WHERE substr(started_at, 1, 10) != date OR ended_at < started_at"
        )
        self.assertEqual(mismatched["rows"][0][0], 0)

    def test_question_counts_match_transcripts(self) -> None:
        mismatched = self.database.execute_readonly_query(
            "SELECT COUNT(*) FROM games g WHERE g.questions_asked != "
            "(SELECT COUNT(*) FROM questions q WHERE q.game_id = g.game_id)"
        )
        self.assertEqual(mismatched["rows"][0][0], 0)

    def test_dev_has_history_and_every_state_today(self) -> None:
        history = self.database.get_history(self.summary["dev_user_id"])
        played_dates = {date.fromisoformat(game["date"]) for game in history}
        self.assertIn(self.today - timedelta(days=1), played_dates)

        today_results = {
            game["result"] for game in history if game["date"] == self.today.isoformat()
        }
        self.assertEqual(today_results, {"win", "loss", None})

        today_games = sum(1 for game in history if game["date"] == self.today.isoformat())
        today_puzzles = len(self.summary["topic_slugs"]) * 2
        self.assertLess(today_games, today_puzzles, "some puzzles stay unplayed for live play")

    def test_failed_topic_is_seeded_for_dev(self) -> None:
        failed = self.database.get_topics_with_status("failed")
        self.assertEqual([topic["user_id"] for topic in failed], [self.summary["dev_user_id"]])

    def test_friends_have_completed_games_today(self) -> None:
        completed_today = self.database.execute_readonly_query(
            "SELECT COUNT(*) FROM games g "
            "JOIN friends f ON f.friend_id = g.user_id "
            f"WHERE f.user_id = {self.summary['dev_user_id']} "
            f"AND g.date = '{self.today.isoformat()}' AND g.result IS NOT NULL"
        )
        self.assertGreater(completed_today["rows"][0][0], 0)

    def test_dev_has_recent_shared_wins(self) -> None:
        results = self.database.get_recent_results(self.summary["dev_user_id"])
        self.assertGreater(len(results), 0)
        self.assertTrue(all(result["friends"] for result in results))

    def test_friends_lost_puzzles_dev_finished(self) -> None:
        results = self.database.get_recent_results(self.summary["dev_user_id"], limit=10)
        friend_results = {
            (result["date"], friend["result"])
            for result in results for friend in result["friends"]
        }
        self.assertIn((self.today.isoformat(), "loss"), friend_results)
        yesterday = (self.today - timedelta(days=1)).isoformat()
        self.assertIn((yesterday, "loss"), friend_results)

    def test_answers_use_llm_vocabulary(self) -> None:
        invalid = self.database.execute_readonly_query(
            "SELECT COUNT(*) FROM questions "
            "WHERE answer NOT IN ('yes', 'no', 'partially', 'depends', 'win')"
        )
        self.assertEqual(invalid["rows"][0][0], 0)

    def test_all_accounts_have_avatars(self) -> None:
        accounts = self.database.get_all_accounts()
        self.assertGreater(len(accounts), 0)
        for account in accounts:
            self.assertGreaterEqual(account["avatar_version"], 1)
            thumbnail = Path(self.temporary_directory.name).joinpath(
                "avatars", f"{account['player_code']}.webp",
            )
            self.assertTrue(thumbnail.is_file(), account["username"])

    def test_winning_games_end_with_win_answer(self) -> None:
        mismatched = self.database.execute_readonly_query(
            "SELECT COUNT(*) FROM games g JOIN questions q ON q.game_id = g.game_id "
            "AND q.question_number = g.questions_asked "
            "WHERE (g.result = 'win') != (q.answer = 'win')"
        )
        self.assertEqual(mismatched["rows"][0][0], 0)


if __name__ == "__main__":
    unittest.main()
