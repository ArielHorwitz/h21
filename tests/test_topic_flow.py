from __future__ import annotations

import asyncio
import tempfile
import unittest
from datetime import date
from pathlib import Path
from typing import Optional
from unittest import mock

from fastapi import HTTPException

from h21 import main
from h21.db import GameDatabase
from h21.llm import LLMError


class FakeLLMClient:
    """Answers generation, validation, preview and hint prompts by difficulty.

    `kept` maps difficulty to how many solutions each validation keeps (the
    rest are rejected); `errors` maps difficulty to how many generation calls
    fail before succeeding.
    """

    def __init__(self, kept: dict[str, int], errors: Optional[dict[str, int]] = None) -> None:
        self.kept = kept
        self.errors = dict(errors or {})
        self.generation_calls: dict[str, int] = {}
        self.counter = 0

    @staticmethod
    def _difficulty(prompt: str) -> str:
        return "expert" if "The subject should be obscure" in prompt else "normal"

    async def ask(self, system_prompt: str, user_message: str) -> str:
        if user_message == "Generate the subjects.":
            difficulty = self._difficulty(system_prompt)
            self.generation_calls[difficulty] = self.generation_calls.get(difficulty, 0) + 1
            if self.errors.get(difficulty, 0) > 0:
                self.errors[difficulty] -= 1
                raise LLMError("fake failure", "fake failure")
            names = []
            for _ in range(100):
                self.counter += 1
                names.append(f"{difficulty} solution {self.counter}")
            return "\n".join(names)
        if user_message == "Review the subjects.":
            difficulty = self._difficulty(system_prompt)
            names = [line[2:] for line in system_prompt.split("Subjects to review:\n", 1)[1].splitlines()]
            keep = self.kept[difficulty]
            return "\n".join(
                f"KEEP {name}" if index < keep else f"REJECT {name} | too obscure"
                for index, name in enumerate(names)
            )
        if user_message == "Pick the solutions.":
            candidates = [line[2:] for line in system_prompt.split("Possible solutions:\n", 1)[1].splitlines()]
            return "\n".join(candidates[:5])
        if user_message == "Generate the hints.":
            return "\n".join(f"Hint {number}" for number in range(1, 6))
        raise AssertionError(f"unexpected prompt: {user_message}")


class TopicFlowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database = GameDatabase(Path(self.temporary_directory.name).joinpath("h21.db"))
        self.database.ensure_schema()
        self.database.add_topic("jazz", "Jazz")
        patcher = mock.patch.object(main, "database", self.database, create=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self) -> None:
        self.database.close()
        self.temporary_directory.cleanup()

    def use_client(self, client: FakeLLMClient) -> None:
        patcher = mock.patch.object(main, "llm_client", client, create=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_build(self) -> None:
        async def build() -> None:
            main._start_topic_build("jazz", "Jazz")
            await asyncio.gather(*list(main._background_tasks))
        asyncio.run(build())

    def test_both_difficulties_pass(self) -> None:
        self.use_client(FakeLLMClient(kept={"normal": 80, "expert": 60}))
        self.run_build()
        self.assertEqual(self.database.get_topic("jazz")["status"], "ready")
        self.assertEqual(self.database.get_series_status("jazz", "normal"), "available")
        self.assertEqual(self.database.get_series_status("jazz", "expert"), "available")
        # The preview takes five from the normal pool and keeps them as known solutions.
        preview = self.database.get_preview_solutions("jazz")
        self.assertEqual(len(preview), main.PREVIEW_SIZE)
        self.assertEqual(self.database.pool_count("jazz", "normal"), 80 - main.PREVIEW_SIZE)
        self.assertTrue(set(preview) <= set(self.database.get_all_known_solutions("jazz")))

    def test_short_difficulty_is_retried_then_left_out(self) -> None:
        client = FakeLLMClient(kept={"normal": 80, "expert": 20})
        self.use_client(client)
        self.run_build()
        self.assertEqual(client.generation_calls["expert"], 2)
        self.assertEqual(client.generation_calls["normal"], 1)
        self.assertEqual(self.database.get_topic("jazz")["status"], "ready")
        self.assertEqual(self.database.get_series_status("jazz", "expert"), "unavailable")

    def test_topic_turned_down_with_counts(self) -> None:
        self.use_client(FakeLLMClient(kept={"normal": 15, "expert": 10}))
        self.run_build()
        topic = self.database.get_topic("jazz")
        self.assertEqual(topic["status"], "failed")
        self.assertIn("30 normal", topic["status_detail"])
        self.assertIn("20 expert", topic["status_detail"])

    def test_one_error_is_retried(self) -> None:
        self.use_client(FakeLLMClient(kept={"normal": 80, "expert": 80}, errors={"expert": 1}))
        self.run_build()
        self.assertEqual(self.database.get_topic("jazz")["status"], "ready")

    def test_two_errors_fail_the_build(self) -> None:
        self.use_client(FakeLLMClient(kept={"normal": 80, "expert": 80}, errors={"expert": 2}))
        self.run_build()
        topic = self.database.get_topic("jazz")
        self.assertEqual(topic["status"], "failed")
        self.assertEqual(topic["status_detail"], main.TOPIC_BUILD_FAILED_DETAIL)

    def test_low_refill_winds_down_and_the_last_puzzle_finishes(self) -> None:
        self.database.set_topic_status("jazz", "ready")
        self.database.set_series_status("jazz", "normal", "available")
        self.database.insert_pool_solutions("jazz", "normal", ["Miles Davis"])
        self.use_client(FakeLLMClient(kept={"normal": 3, "expert": 3}))

        async def scenario() -> tuple[str, Optional[str], Optional[str]]:
            with mock.patch.object(main, "date_type") as fake_date:
                fake_date.today.return_value = date(2026, 10, 10)
                first = await main.get_today_solution("jazz", "normal")
                await asyncio.gather(*list(main._background_tasks))
                status_after_refill = self.database.get_series_status("jazz", "normal")
                # Draw the remaining pool, one day at a time.
                day = 11
                while self.database.pool_count("jazz", "normal") > 0:
                    fake_date.today.return_value = date(2026, 10, day)
                    await main.get_today_solution("jazz", "normal")
                    day += 1
                status_after_last = self.database.get_series_status("jazz", "normal")
            return first, status_after_refill, status_after_last

        first, status_after_refill, status_after_last = asyncio.run(scenario())
        self.assertEqual(first, "Miles Davis")
        self.assertEqual(status_after_refill, "winding_down")
        self.assertEqual(status_after_last, "finished")

    def test_empty_available_pool_recovers(self) -> None:
        self.database.set_topic_status("jazz", "ready")
        self.database.set_series_status("jazz", "normal", "available")
        self.use_client(FakeLLMClient(kept={"normal": 60, "expert": 60}))

        async def scenario() -> str:
            with mock.patch.object(main, "date_type") as fake_date:
                fake_date.today.return_value = date(2026, 10, 10)
                return await main.get_today_solution("jazz", "normal")

        self.assertTrue(asyncio.run(scenario()).startswith("normal solution"))

    def test_unavailable_series_is_not_playable(self) -> None:
        self.database.set_topic_status("jazz", "ready")
        self.database.set_series_status("jazz", "expert", "unavailable")
        self.use_client(FakeLLMClient(kept={"normal": 60, "expert": 60}))
        with self.assertRaises(HTTPException) as raised:
            asyncio.run(main.get_today_solution("jazz", "expert"))
        self.assertEqual(raised.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
