from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from typing import Optional
from unittest import mock

from fastapi import HTTPException
from starlette.requests import Request

from h21 import main
from h21.db import GameDatabase

MONDAY = date(2026, 10, 12)
TUESDAY = date(2026, 10, 13)


def make_request(user_id: int, time_zone: Optional[str] = None) -> Request:
    headers = [(b"cookie", f"tz={time_zone}".encode())] if time_zone else []
    request = Request({"type": "http", "method": "GET", "path": "/", "headers": headers})
    request.state.user_id = user_id
    return request


class PlayerDateTests(unittest.TestCase):
    def test_dates_follow_the_time_zone_cookie(self) -> None:
        # Kiritimati (UTC+14) and Pago Pago (UTC-11) are 25 hours apart.
        ahead = main.player_today(make_request(1, "Pacific/Kiritimati"))
        behind = main.player_today(make_request(1, "Pacific/Pago_Pago"))
        self.assertIn((ahead - behind).days, (1, 2))

    def test_unknown_time_zones_fall_back_to_utc(self) -> None:
        utc_today = main.player_today(make_request(1))
        for bad_zone in ("Mars/Olympus_Mons", "../../etc/passwd"):
            self.assertEqual(main.player_today(make_request(1, bad_zone)), utc_today)


class CarriedOverGameTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database = GameDatabase(Path(self.temporary_directory.name).joinpath("h21.db"))
        self.database.ensure_schema()
        self.database.add_topic("jazz", "Jazz")
        self.database.set_topic_status("jazz", "ready")
        self.database.set_series_status("jazz", "normal", "available")
        for day, solution in ((MONDAY, "Miles Davis"), (TUESDAY, "Nina Simone")):
            self.database.record_puzzle(day, "jazz", "normal", solution, hints=[f"Hint {i}" for i in range(5)])
        self.user_id = self.database.create_account(
            "player", "secret", daily_question_limit=200, daily_topic_limit=2,
        )
        patcher = mock.patch.object(main, "database", self.database, create=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self) -> None:
        self.database.close()
        self.temporary_directory.cleanup()

    def on(self, day: date) -> mock._patch:
        return mock.patch.object(main, "player_today", return_value=day)

    def start_game(self) -> dict:
        request = make_request(self.user_id)
        return asyncio.run(main.new_game(main.NewGameRequest(topic_slug="jazz", difficulty="normal"), request))

    def existing_game(self) -> Optional[dict]:
        response = asyncio.run(main.get_existing_game(make_request(self.user_id), "jazz", "normal"))
        if response.status_code == 204:
            return None
        return json.loads(response.body)

    def test_an_open_game_carries_over_and_holds_the_new_puzzle(self) -> None:
        with self.on(MONDAY):
            game_id = self.start_game()["game_id"]
        self.database.record_question(game_id, 1, "Is it a person?", "yes")

        with self.on(TUESDAY):
            game = self.existing_game()
            self.assertEqual(game["game_id"], game_id)
            self.assertEqual(game["date"], MONDAY.isoformat())
            self.assertTrue(game["new_puzzle_waiting"])
            with self.assertRaises(HTTPException) as raised:
                self.start_game()
            self.assertEqual(raised.exception.status_code, 409)

            # Ending it (on Tuesday) reveals Monday's solution and frees the series.
            ended = asyncio.run(main.end_game(main.EndGameRequest(game_id=game_id, result="loss"), make_request(self.user_id)))
            self.assertEqual(ended["solution"], "Miles Davis")
            self.assertIsNone(self.existing_game())
            new_game_id = self.start_game()["game_id"]
            self.assertEqual(self.database.get_game(new_game_id)["date"], TUESDAY.isoformat())

    def test_an_untouched_game_from_another_day_is_dropped(self) -> None:
        with self.on(MONDAY):
            game_id = self.start_game()["game_id"]
        with self.on(TUESDAY):
            self.assertIsNone(self.existing_game())
            self.start_game()
        self.assertIsNone(self.database.get_game(game_id))

    def test_a_finished_game_cannot_be_played_on(self) -> None:
        with self.on(MONDAY):
            game_id = self.start_game()["game_id"]
            asyncio.run(main.end_game(main.EndGameRequest(game_id=game_id, result="loss"), make_request(self.user_id)))
            with self.assertRaises(HTTPException) as raised:
                asyncio.run(main.get_hint(main.HintRequest(game_id=game_id, hint_index=0), make_request(self.user_id)))
            self.assertEqual(raised.exception.status_code, 409)

    def test_open_games_keep_their_solution_out_of_history(self) -> None:
        with self.on(MONDAY):
            game_id = self.start_game()["game_id"]
        self.database.record_question(game_id, 1, "Is it a person?", "yes")
        self.assertIsNone(self.database.get_history(self.user_id)[0]["solution"])


class UsageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database = GameDatabase(Path(self.temporary_directory.name).joinpath("h21.db"))
        self.database.ensure_schema()
        self.user_id = self.database.create_account(
            "player", "secret", daily_question_limit=200, daily_topic_limit=2, monthly_avatar_limit=3,
        )

    def tearDown(self) -> None:
        self.database.close()
        self.temporary_directory.cleanup()

    def test_pictures_count_per_local_month(self) -> None:
        self.database.increment_avatar_generation(self.user_id, date(2026, 9, 30))
        self.database.increment_avatar_generation(self.user_id, date(2026, 10, 1))
        self.database.increment_avatar_generation(self.user_id, date(2026, 10, 13))
        self.assertEqual(self.database.get_avatar_usage(self.user_id, date(2026, 10, 20))["used"], 2)
        self.assertEqual(self.database.get_avatar_usage(self.user_id, date(2026, 11, 1))["used"], 0)

    def test_reset_clears_the_day_and_the_month(self) -> None:
        self.database.increment_daily_questions(self.user_id, TUESDAY)
        self.database.increment_daily_questions(self.user_id, MONDAY)
        self.database.increment_avatar_generation(self.user_id, MONDAY)
        self.database.reset_daily_usage(self.user_id, TUESDAY)
        self.assertEqual(self.database.get_daily_usage(self.user_id, TUESDAY)["questions_used"], 0)
        self.assertEqual(self.database.get_daily_usage(self.user_id, MONDAY)["questions_used"], 1)
        self.assertEqual(self.database.get_avatar_usage(self.user_id, TUESDAY)["used"], 0)


if __name__ == "__main__":
    unittest.main()
