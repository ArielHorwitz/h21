from __future__ import annotations

import asyncio
import unittest

from h21.llm import LLMError, generate_solution_batch, validate_solution_batch

BATCH = [f"Musician {number}" for number in range(1, 101)]


class ScriptedClient:
    def __init__(self, reply: str) -> None:
        self.reply = reply

    async def ask(self, system_prompt: str, user_message: str) -> str:
        return self.reply


def generate(reply: str) -> list[str]:
    batch = asyncio.run(generate_solution_batch(ScriptedClient(reply), [], "Jazz", "normal", batch_size=100))
    return batch.solutions


def validate(reply: str) -> list:
    return asyncio.run(validate_solution_batch(ScriptedClient(reply), BATCH, [], "Jazz", "normal")).results


class GenerationChecksTests(unittest.TestCase):
    def test_a_refusal_is_an_error(self) -> None:
        with self.assertRaises(LLMError):
            generate("I can't comply with this request.")

    def test_too_few_names_is_an_error(self) -> None:
        with self.assertRaises(LLMError):
            generate("\n".join(BATCH[:40]))
        self.assertEqual(generate("\n".join(BATCH[:60])), BATCH[:60])


class ValidationChecksTests(unittest.TestCase):
    def test_only_names_from_the_batch_are_kept(self) -> None:
        reply = "\n".join(f"KEEP {name.upper()}" for name in BATCH) + "\nKEEP I can't comply with this request."
        results = validate(reply)
        self.assertEqual([result.solution for result in results], BATCH)

    def test_a_refusal_is_an_error(self) -> None:
        with self.assertRaises(LLMError):
            validate("I have nothing to accept or reject.")

    def test_too_few_verdicts_is_an_error(self) -> None:
        with self.assertRaises(LLMError):
            validate("\n".join(f"KEEP {name}" for name in BATCH[:80]))

    def test_first_verdict_wins(self) -> None:
        reply = "\n".join(f"REJECT {name} | too obscure" for name in BATCH) + f"\nKEEP {BATCH[0]}"
        self.assertFalse(any(result.kept for result in validate(reply)))


if __name__ == "__main__":
    unittest.main()
