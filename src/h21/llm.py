from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol

from openai import AsyncOpenAI

LEGAL_RESPONSES = frozenset({"yes", "no", "partially", "depends", "win"})

SYSTEM_PROMPT_TEMPLATE = """\
You are the host of a game of 21 questions. The secret solution is: "{solution}".
The solution is a historical figure, event, or place.

The player will ask you questions or make guesses. You must decide on EXACTLY
one answer — one of: yes, no, partially, depends, win.

- "yes" if the answer to their question is clearly yes.
- "no" if the answer is clearly no.
- "partially" if the answer is partly correct or context-dependent.
- "depends" if the answer varies based on interpretation or framing.
- "win" ONLY if the player has correctly identified the secret solution.

First, briefly explain your reasoning (1-3 sentences). Do not reveal the \
solution or its name in your explanation. Then, on the LAST line, write ONLY \
your one-word answer.

The player may ask questions in ANY language. Regardless of what language the \
question is in, your final answer on the last line MUST always be one of the \
five English words above. Your explanation may be in any language.\
"""


class LLMClient(Protocol):
    async def ask(
        self,
        system_prompt: str,
        user_message: str,
        *,
        max_tokens: int = 10,
        temperature: float = 0.0,
    ) -> str: ...


class OpenAIClient:
    def __init__(self, api_key: str) -> None:
        self._client = AsyncOpenAI(api_key=api_key)

    async def ask(
        self,
        system_prompt: str,
        user_message: str,
        *,
        max_tokens: int = 10,
        temperature: float = 0.0,
    ) -> str:
        response = await self._client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return response.choices[0].message.content or ""


GENERATE_SOLUTION_PROMPT = """\
You are helping create daily puzzles for a history-themed 21 questions game.

Generate a single historical subject — a well-known historical figure, event, \
or place — that would work well as a 21-questions answer. The subject should be \
famous enough that an educated person could reasonably guess it within 21 yes/no \
questions.

Reply with ONLY the name of the subject. No quotes, no explanation, no \
punctuation beyond what the name itself requires.\
"""


async def generate_solution(
    client: LLMClient, previous_solutions: list[str]
) -> str:
    """Ask the LLM to generate a new daily solution, avoiding repeats."""
    prompt = GENERATE_SOLUTION_PROMPT
    if previous_solutions:
        formatted = "\n".join(f"- {solution}" for solution in previous_solutions)
        prompt += (
            "\n\nThe following subjects have already been used. "
            "Do NOT repeat any of them:\n" + formatted
        )

    response = await client.ask(
        prompt, "Generate a new historical subject.",
        max_tokens=50, temperature=0.8,
    )
    return response.strip().strip('"').strip("'")


@dataclass
class AnswerResult:
    answer: str
    explanation: str


async def ask_question(
    client: LLMClient, question: str, secret_solution: str
) -> Optional[AnswerResult]:
    """Ask the LLM a question about the secret solution.

    Returns an AnswerResult with the answer and explanation, or None if
    the LLM gave an unparseable response.
    """
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(solution=secret_solution)
    raw_response = await client.ask(system_prompt, question, max_tokens=200)
    lines = raw_response.strip().splitlines()
    answer = lines[-1].strip().lower().rstrip(".")
    if answer not in LEGAL_RESPONSES:
        return None
    explanation = "\n".join(lines[:-1]).strip()
    return AnswerResult(answer=answer, explanation=explanation)
