from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

from h21.db import GameDatabase
from h21.llm import _parse_line_per_solution


class ParseLinePerSubjectTests(unittest.TestCase):
    def test_strips_list_markers_and_quotes(self) -> None:
        response = "1. Apollo 11\n2) “Across the Universe”\n- 'Hey Jude'\n* Mir\n\n"
        self.assertEqual(
            _parse_line_per_solution(response),
            ["Apollo 11", "Across the Universe", "Hey Jude", "Mir"],
        )

    def test_keeps_leading_digits_that_belong_to_the_solution(self) -> None:
        response = "1984\n2001: A Space Odyssey\n1948 Arab-Israeli War"
        self.assertEqual(
            _parse_line_per_solution(response),
            ["1984", "2001: A Space Odyssey", "1948 Arab-Israeli War"],
        )


class PuzzlePoolDatabaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database = GameDatabase(Path(self.temporary_directory.name).joinpath("h21.db"))
        self.database.ensure_schema()
        self.creator_id = self._create_account("creator")
        self.other_id = self._create_account("other")

    def tearDown(self) -> None:
        self.database.close()
        self.temporary_directory.cleanup()

    def _create_account(self, username: str) -> int:
        return self.database.create_account(
            username, "password", daily_question_limit=10, daily_topic_limit=1,
        )

    def test_default_topics_start_generating(self) -> None:
        slugs = {topic["slug"] for topic in self.database.get_topics_with_status("generating")}
        self.assertEqual(slugs, {"notable-people", "world-geography"})

    def test_unready_topics_are_only_listed_for_their_creator(self) -> None:
        self.database.add_topic("jazz", "Jazz", user_id=self.creator_id)
        today = date(2026, 10, 10)
        creator_slugs = {topic["slug"] for topic in self.database.get_topics_ranked(self.creator_id, today)}
        other_slugs = {topic["slug"] for topic in self.database.get_topics_ranked(self.other_id, today)}
        self.assertIn("jazz", creator_slugs)
        self.assertNotIn("jazz", other_slugs)

        self.database.set_topic_status("jazz", "ready")
        other_slugs = {topic["slug"] for topic in self.database.get_topics_ranked(self.other_id, today)}
        self.assertIn("jazz", other_slugs)

    def test_cross_difficulty_duplicates_are_removed_from_expert(self) -> None:
        self.database.add_topic("jazz", "Jazz", user_id=self.creator_id)
        self.database.insert_pool_solutions("jazz", "normal", ["Miles Davis", "Bebop"])
        self.database.insert_pool_solutions("jazz", "expert", ["Bebop", "Sun Ra"])
        self.assertEqual(self.database.remove_cross_difficulty_pool_duplicates("jazz"), 1)
        self.assertEqual(self.database.pool_count("jazz", "normal"), 2)
        self.assertEqual(self.database.pool_count("jazz", "expert"), 1)

    def test_draw_removes_solution_from_pool(self) -> None:
        self.database.add_topic("jazz", "Jazz", user_id=self.creator_id)
        self.database.insert_pool_solutions("jazz", "normal", ["Miles Davis"])
        self.assertEqual(self.database.draw_random_from_pool("jazz", "normal"), "Miles Davis")
        self.assertIsNone(self.database.draw_random_from_pool("jazz", "normal"))

    def test_last_pool_refill_is_most_recent(self) -> None:
        self.database.add_topic("jazz", "Jazz", user_id=self.creator_id)
        self.assertIsNone(self.database.get_last_pool_refill("jazz", "normal"))
        self.database.record_pool_refill("jazz", "normal", generated=100, kept=80)
        self.database.record_pool_refill("jazz", "normal", generated=100, kept=4)
        self.assertEqual(self.database.get_last_pool_refill("jazz", "normal")["kept"], 4)

    def test_delete_topic_removes_pool_and_refills(self) -> None:
        self.database.add_topic("jazz", "Jazz", user_id=self.creator_id)
        self.database.insert_pool_solutions("jazz", "normal", ["Miles Davis"])
        self.database.record_pool_refill("jazz", "normal", generated=100, kept=1)
        self.database.delete_topic("jazz")
        self.assertIsNone(self.database.get_topic("jazz"))
        self.assertEqual(self.database.pool_count("jazz", "normal"), 0)
        self.assertIsNone(self.database.get_last_pool_refill("jazz", "normal"))


if __name__ == "__main__":
    unittest.main()
