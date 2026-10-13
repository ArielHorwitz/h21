from __future__ import annotations

import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from h21.db import GameDatabase
from h21.sandbox import BLOCKED_PERSONA, ADMIN_USERNAME, NO_PICTURE_PERSONA, add_activity, seed_database


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

    def test_admin_account_exists_and_authenticates(self) -> None:
        account = self.database.get_account_by_username(ADMIN_USERNAME)
        self.assertIsNotNone(account)
        self.assertEqual(account["role"], "admin")
        self.assertEqual(
            self.database.authenticate(ADMIN_USERNAME, "test-password"),
            self.summary["admin_user_id"],
        )

    def test_series_cover_every_state(self) -> None:
        self.assertGreater(self.summary["pooled_count"], 0)
        states = self.summary["series_states"]
        expected_status = {
            "finished": "finished", "topic_finished": "finished",
            "last_puzzle": "winding_down", "winding_down": "winding_down",
        }
        for state, status in expected_status.items():
            self.assertIn(state, states)
            self.assertEqual(self.database.get_series_status(*states[state]), status)
        self.assertEqual(self.database.pool_count(*states["last_puzzle"]), 0)
        self.assertIsNotNone(self.database.get_puzzle_solution(self.today, *states["last_puzzle"]))
        self.assertIsNone(self.database.get_puzzle_solution(self.today, *states["finished"]))
        flagged = [series for series in self.database.get_all_series() if series["needs_attention"]]
        self.assertEqual(len(flagged), 1)

    def test_friend_connections_are_mutual(self) -> None:
        admin_id = self.summary["admin_user_id"]
        friends = self.database.get_friends(admin_id)
        friend_usernames = {friend["username"] for friend in friends}
        expected = set(self.summary["friend_usernames"])
        expected.add(self.summary["anonymous_username"])
        self.assertEqual(friend_usernames, expected)
        for friend in friends:
            followed_back = {
                entry["user_id"]
                for entry in self.database.get_friends(friend["user_id"])
            }
            self.assertIn(admin_id, followed_back)

    def test_friend_suggestions_cover_follower_and_friend_of_friend(self) -> None:
        suggestions = self.database.get_friend_suggestions(self.summary["admin_user_id"])
        suggested = {entry["username"]: entry["tier"] for entry in suggestions}
        self.assertEqual(suggested.get(self.summary["follower_username"]), 1)
        self.assertEqual(suggested.get(self.summary["friend_of_friend_username"]), 2)

    def test_every_game_has_a_matching_puzzle(self) -> None:
        orphans = self.database.execute_readonly_query(
            "SELECT COUNT(*) FROM games g "
            "LEFT JOIN puzzles dp ON dp.date = g.date "
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

    def test_admin_has_history_and_every_state_today(self) -> None:
        history = self.database.get_history(self.summary["admin_user_id"])
        played_dates = {date.fromisoformat(game["date"]) for game in history}
        self.assertIn(self.today - timedelta(days=1), played_dates)

        today_results = {
            game["result"] for game in history if game["date"] == self.today.isoformat()
        }
        self.assertEqual(today_results, {"win", "loss", None})

        today_games = sum(1 for game in history if game["date"] == self.today.isoformat())
        today_puzzles = len(self.summary["topic_slugs"]) * 2
        self.assertLess(today_games, today_puzzles, "some puzzles stay unplayed for live play")

    def test_turned_down_topics_for_several_players(self) -> None:
        failed = self.database.get_topics_with_status("failed")
        suggesters = {topic["user_id"] for topic in failed}
        self.assertIn(self.summary["admin_user_id"], suggesters)
        self.assertGreater(len(suggesters), 1)

    def test_friends_have_completed_games_today(self) -> None:
        completed_today = self.database.execute_readonly_query(
            "SELECT COUNT(*) FROM games g "
            "JOIN friends f ON f.friend_id = g.user_id "
            f"WHERE f.user_id = {self.summary['admin_user_id']} "
            f"AND g.date = '{self.today.isoformat()}' AND g.result IS NOT NULL"
        )
        self.assertGreater(completed_today["rows"][0][0], 0)

    def test_admin_has_recent_shared_wins(self) -> None:
        results = self.database.get_recent_results(self.summary["admin_user_id"])
        self.assertGreater(len(results), 0)
        self.assertTrue(all(result["friends"] for result in results))

    def test_friends_lost_puzzles_admin_solved(self) -> None:
        for day in (self.today, self.today - timedelta(days=1)):
            losses = self.database.execute_readonly_query(
                "SELECT COUNT(*) FROM games g "
                "JOIN friends f ON f.friend_id = g.user_id "
                "JOIN games mine ON mine.user_id = f.user_id AND mine.date = g.date "
                "  AND mine.topic_slug = g.topic_slug AND mine.difficulty = g.difficulty "
                f"WHERE f.user_id = {self.summary['admin_user_id']} "
                f"AND g.date = '{day.isoformat()}' AND g.result = 'loss' AND mine.result = 'win'"
            )
            self.assertGreater(losses["rows"][0][0], 0, day)

    def test_unsolved_games_stay_out_of_recent_results(self) -> None:
        results = self.database.get_recent_results(self.summary["admin_user_id"], limit=10)
        self.assertGreater(len(results), 0)
        for result in results:
            for friend in result["friends"]:
                outcome = self.database.execute_readonly_query(
                    "SELECT g.result FROM games g JOIN accounts a ON a.user_id = g.user_id "
                    f"WHERE a.player_code = '{friend['player_code']}' AND g.date = '{result['date']}' "
                    f"AND g.topic_slug = '{result['topic_slug']}' AND g.difficulty = '{result['difficulty']}'"
                )
                self.assertEqual(outcome["rows"], [["win"]])

    def test_blocked_accounts_are_never_suggested_or_found(self) -> None:
        blocked = self.database.get_account_by_username(BLOCKED_PERSONA[0])
        self.assertTrue(blocked["blocked"])
        admin_id = self.summary["admin_user_id"]
        suggested = {entry["username"] for entry in self.database.get_friend_suggestions(admin_id)}
        self.assertNotIn(BLOCKED_PERSONA[0], suggested)
        found = {entry["username"] for entry in self.database.search_players(BLOCKED_PERSONA[0], exclude_user_id=admin_id)}
        self.assertNotIn(BLOCKED_PERSONA[0], found)

    def test_answers_use_llm_vocabulary(self) -> None:
        invalid = self.database.execute_readonly_query(
            "SELECT COUNT(*) FROM questions "
            "WHERE answer NOT IN ('yes', 'no', 'partially', 'depends', 'win')"
        )
        self.assertEqual(invalid["rows"][0][0], 0)

    def test_accounts_have_avatars_except_the_one_without(self) -> None:
        accounts = self.database.get_all_accounts()
        self.assertGreater(len(accounts), 0)
        for account in accounts:
            if account["username"] == NO_PICTURE_PERSONA[0]:
                self.assertEqual(account["avatar_version"], 0)
                continue
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


class SandboxAddActivityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temporary_directory.name).joinpath("h21.db")
        self.today = date(2026, 8, 28)
        seed_database(self.db_path, password="test-password", rng_seed=21, today=self.today)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def _games(self, database: GameDatabase) -> list[list]:
        return database.execute_readonly_query(
            "SELECT a.username, g.date, g.topic_slug, g.difficulty, g.result "
            "FROM games g JOIN accounts a ON a.user_id = g.user_id"
        )["rows"]

    def test_adds_games_for_personas_without_duplicates(self) -> None:
        database = GameDatabase(self.db_path)
        before = self._games(database)
        database.close()

        tomorrow = self.today + timedelta(days=1)
        summary = add_activity(self.db_path, rng_seed=5, today=tomorrow)
        add_activity(self.db_path, rng_seed=6, today=tomorrow)

        database = GameDatabase(self.db_path)
        after = self._games(database)
        database.close()
        self.assertGreater(len(summary["games"]), 0)
        self.assertTrue(all(game["username"] != ADMIN_USERNAME for game in summary["games"]))
        # Existing games are untouched and no one plays a puzzle twice.
        self.assertEqual(after[:len(before)], before)
        puzzles_played = [(row[0], row[1], row[2], row[3]) for row in after]
        self.assertEqual(len(puzzles_played), len(set(puzzles_played)))


class SandboxIntoExistingDataTests(unittest.TestCase):
    def test_existing_accounts_and_topics_are_kept(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            db_path = Path(temporary_directory).joinpath("h21.db")
            database = GameDatabase(db_path)
            database.ensure_schema()
            admin_id = database.create_account(
                ADMIN_USERNAME, "own-password", role="admin", daily_question_limit=5, daily_topic_limit=1,
            )
            database.add_topic("roman-history", "Roman History", user_id=admin_id, status="ready")
            database.insert_pool_solutions("roman-history", "normal", [f"Emperor {number}" for number in range(60)])
            database.set_series_status("roman-history", "normal", "available")
            database.set_series_status("roman-history", "expert", "unavailable")
            database.set_preview_solutions("roman-history", ["Emperor 1", "Emperor 2", "Emperor 3", "Emperor 4", "Emperor 5"])
            topic_created_at = lambda db: db.execute_readonly_query(
                "SELECT created_at FROM topics WHERE slug = 'roman-history'"
            )["rows"][0][0]
            created_at = topic_created_at(database)
            database.close()

            seed_database(db_path, password="test-password", rng_seed=21, today=date(2026, 8, 28))

            database = GameDatabase(db_path)
            self.assertIsNotNone(database.authenticate(ADMIN_USERNAME, "own-password"))
            self.assertEqual(database.get_account_by_username(ADMIN_USERNAME)["user_id"], admin_id)
            self.assertEqual(database.get_series_status("roman-history", "expert"), "unavailable")
            self.assertEqual(database.get_preview_solutions("roman-history")[0], "Emperor 1")
            self.assertEqual(topic_created_at(database), created_at)
            self.assertGreater(len(database.get_friends(admin_id)), 0)
            database.close()
