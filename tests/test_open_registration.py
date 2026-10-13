from __future__ import annotations

import asyncio
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

from fastapi import HTTPException

from h21 import main
from h21.db import GameDatabase


class OpenRegistrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database = GameDatabase(Path(self.temporary_directory.name).joinpath("h21.db"))
        self.database.ensure_schema()
        patches = {
            "database": self.database,
            "signing_secret": "test-secret",
            "secure_cookies": False,
            "default_daily_question_limit": 500,
            "default_daily_topic_limit": 3,
            "default_monthly_avatar_limit": 3,
        }
        for name, value in patches.items():
            patcher = mock.patch.object(main, name, value, create=True)
            patcher.start()
            self.addCleanup(patcher.stop)
        # Registration starts a picture in the background; not under test here.
        patcher = mock.patch.object(main, "_generate_registration_avatar", mock.AsyncMock())
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self) -> None:
        self.database.close()
        self.temporary_directory.cleanup()

    def register(self, username: str, invite_code: str = "") -> int:
        async def run() -> int:
            await main.register(main.RegisterRequest(
                username=username, password="secret", invite_code=invite_code,
            ))
            return self.database.get_account_by_username(username)["user_id"]
        return asyncio.run(run())

    def test_open_signup_gets_the_open_quotas(self) -> None:
        user_id = self.register("newcomer")
        account = self.database.get_account_by_id(user_id)
        self.assertIsNone(account["invite_code"])
        self.assertEqual(account["role"], "user")
        self.assertEqual(account["daily_question_limit"], 200)
        self.assertEqual(account["daily_topic_limit"], 2)
        self.assertEqual(account["monthly_avatar_limit"], 3)

    def test_open_spots_run_out_but_invites_still_work(self) -> None:
        self.database.set_setting("open_signups_per_day", 2)
        self.register("first")
        self.register("second")
        with self.assertRaises(HTTPException) as raised:
            self.register("third")
        self.assertEqual(raised.exception.status_code, 403)
        self.assertFalse(asyncio.run(main.open_signups())["available"])
        self.assertTrue(asyncio.run(main.admin_attention())["open_spots_used_up"])

        invite_code = self.database.create_invite()
        user_id = self.register("invited", invite_code)
        self.assertEqual(self.database.get_account_by_id(user_id)["daily_question_limit"], 500)

    def test_zero_turns_open_signups_off(self) -> None:
        self.database.set_setting("open_signups_per_day", 0)
        self.assertFalse(asyncio.run(main.open_signups())["available"])
        with self.assertRaises(HTTPException):
            self.register("newcomer")
        # Turned off on purpose, so it isn't flagged for attention.
        self.assertFalse(asyncio.run(main.admin_attention())["open_spots_used_up"])

    def test_settings_shape_new_accounts(self) -> None:
        asyncio.run(main.update_settings(main.SettingsUpdate(values={"open_signup_daily_topic_limit": 1})))
        user_id = self.register("newcomer")
        self.assertEqual(self.database.get_account_by_id(user_id)["daily_topic_limit"], 1)

    def test_unknown_or_negative_settings_are_refused(self) -> None:
        for values in ({"nonsense": 1}, {"open_signups_per_day": -1}):
            with self.assertRaises(HTTPException) as raised:
                asyncio.run(main.update_settings(main.SettingsUpdate(values=values)))
            self.assertEqual(raised.exception.status_code, 400)

    def test_taken_username_keeps_the_invite(self) -> None:
        self.register("taken")
        invite_code = self.database.create_invite(uses=1)
        with self.assertRaises(HTTPException) as raised:
            self.register("taken", invite_code)
        self.assertEqual(raised.exception.status_code, 409)
        self.register("other", invite_code)

    def test_open_signups_are_counted_per_day(self) -> None:
        self.register("newcomer")
        self.assertEqual(self.database.count_open_signups(main.datetime.now(main.timezone.utc).date()), 1)
        self.assertEqual(self.database.count_open_signups(date(2000, 1, 1)), 0)


class RecentlyActiveSuggestionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database = GameDatabase(Path(self.temporary_directory.name).joinpath("h21.db"))
        self.database.ensure_schema()
        self.database.add_topic("jazz", "Jazz")

    def tearDown(self) -> None:
        self.database.close()
        self.temporary_directory.cleanup()

    def account(self, username: str) -> int:
        return self.database.create_account(
            username, "secret", daily_question_limit=200, daily_topic_limit=2,
        )

    def test_recently_active_players_fill_in(self) -> None:
        newcomer = self.account("newcomer")
        active = self.account("active")
        hidden = self.account("hidden")
        followed = self.account("followed")
        self.account("idle")
        self.database.update_profile(hidden, None, True)
        self.database.add_friend(newcomer, followed)
        for user_id in (active, hidden, followed):
            self.database.create_game(date.today(), "jazz", "normal", user_id=user_id)

        suggestions = self.database.get_friend_suggestions(newcomer)
        self.assertEqual([suggestion["username"] for suggestion in suggestions], ["active"])
        self.assertEqual(suggestions[0]["tier"], 4)


class DefaultPictureTests(unittest.TestCase):
    def test_admins_start_with_the_admin_badge(self) -> None:
        badge = main.avatar_mod.ADMIN_AVATAR_PATH.read_bytes()
        self.assertEqual(asyncio.run(main._default_avatar_bytes("admin")), badge)


if __name__ == "__main__":
    unittest.main()
