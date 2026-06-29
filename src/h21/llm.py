from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional, Protocol

from openai import APIConnectionError, APIStatusError, AsyncOpenAI

logger = logging.getLogger("h21.llm")

LEGAL_RESPONSES = frozenset({"yes", "no", "partially", "depends", "win"})

DIFFICULTY_GUIDANCE = {
    "easy": (
        "The subject should be very well-known — something that someone with "
        "only basic familiarity with the topic would recognize immediately."
    ),
    "medium": (
        "The subject should require moderate familiarity with the topic. "
        "Someone who has studied it casually should be able to guess it."
    ),
    "hard": (
        "The subject should be obscure — something that only someone "
        "intimately familiar with the topic would know."
    ),
}

SYSTEM_PROMPT_TEMPLATE = """\
You are the host of a game of 21 questions. The secret solution is: "{solution}".
The topic is: {topic}. The solution is a notable figure, event, place, or concept \
related to this topic.

The player will ask you questions or make guesses. You must decide on EXACTLY
one answer — one of: yes, no, partially, depends, win.

- "yes" if the answer to their question is clearly yes.
- "no" if the answer is clearly no.
- "partially" if the answer is partly correct or context-dependent.
- "depends" if the answer varies based on interpretation or framing.
- "win" ONLY if the player has correctly identified the secret solution.

Before giving your answer, write a detailed explanation covering the following. \
Do not reveal the solution or its name anywhere in your explanation — refer to \
it indirectly (e.g. "the subject", "this person", "this event").

1. REASONING: Explain why you chose this answer. What facts about the subject \
led you to this conclusion?
2. NUANCE: If applicable, explain what makes the answer not fully \
straightforward — e.g. common misconceptions, edge cases, or historical \
context that complicates a simple yes/no.
3. NEAR MISSES: Suggest how the player could rephrase or narrow their \
question to get a more decisive or useful answer. For example, "If you had \
asked whether they were born in Europe, the answer would be yes" or "Asking \
about the century rather than the exact year would narrow it down faster."

Keep the explanation concise but substantive (3-6 sentences total). Then, on \
the LAST line, write ONLY your one-word answer.

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
        temperature: Optional[float] = None,
    ) -> str: ...


class LLMError(Exception):
    """Raised when an LLM call fails in a way we can describe to the user."""

    def __init__(self, message: str, detail: str) -> None:
        super().__init__(message)
        self.detail = detail


class OpenAIClient:
    def __init__(self, api_key: str, model: str = "gpt-4o") -> None:
        self._client = AsyncOpenAI(api_key=api_key)
        self._model = model

    async def ask(
        self,
        system_prompt: str,
        user_message: str,
        *,
        max_tokens: int = 10,
        temperature: Optional[float] = None,
    ) -> str:
        kwargs: dict = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            "max_completion_tokens": max_tokens,
        }
        if temperature is not None:
            kwargs["temperature"] = temperature

        logger.info(
            "LLM request: model=%s max_tokens=%d user_message=%r",
            self._model, max_tokens, user_message[:200],
        )
        logger.debug(
            "LLM request system_prompt: %s", system_prompt[:500],
        )

        try:
            response = await self._client.chat.completions.create(**kwargs)
        except APIConnectionError:
            logger.exception("LLM connection error")
            raise LLMError(
                "Failed to connect to the AI service",
                "Could not reach the AI service. Please try again later.",
            )
        except APIStatusError as exc:
            logger.error(
                "LLM API error: status=%d body=%s",
                exc.status_code, exc.body,
            )
            if exc.status_code == 429:
                raise LLMError(
                    f"LLM rate limited: {exc.status_code}",
                    "AI service is rate-limited. Please wait a moment and try again.",
                )
            raise LLMError(
                f"LLM API error: {exc.status_code}",
                "AI service returned an error. Please try again later.",
            )

        content = response.choices[0].message.content or ""
        finish_reason = response.choices[0].finish_reason

        logger.info(
            "LLM response: finish_reason=%s length=%d content=%r",
            finish_reason, len(content), content[:300],
        )

        if not content.strip():
            logger.warning("LLM returned empty response")
            raise LLMError(
                "LLM returned empty response",
                "AI returned an empty response. Please try again.",
            )

        return content


GENERATE_SOLUTION_PROMPT_TEMPLATE = """\
You are helping create daily puzzles for a 21-questions trivia game.

The topic is: {topic}.

Generate a single subject — a notable figure, event, place, or concept \
related to this topic — that would work well as a 21-questions answer.

{difficulty_guidance}

Reply with ONLY the name of the subject. No quotes, no explanation, no \
punctuation beyond what the name itself requires.\
"""


async def generate_solution(
    client: LLMClient,
    previous_solutions: list[str],
    topic_name: str,
    difficulty: str,
) -> str:
    """Ask the LLM to generate a new daily solution, avoiding repeats."""
    guidance = DIFFICULTY_GUIDANCE.get(difficulty, DIFFICULTY_GUIDANCE["medium"])
    prompt = GENERATE_SOLUTION_PROMPT_TEMPLATE.format(
        topic=topic_name,
        difficulty_guidance=guidance,
    )
    if previous_solutions:
        formatted = "\n".join(f"- {solution}" for solution in previous_solutions)
        prompt += (
            "\n\nThe following subjects have already been used. "
            "Do NOT repeat any of them:\n" + formatted
        )

    response = await client.ask(
        prompt, "Generate a new subject.",
        max_tokens=50,
    )
    solution = response.strip().strip('"').strip("'")
    if not solution:
        logger.error("LLM generated empty solution after stripping for topic=%r", topic_name)
        raise LLMError(
            "LLM generated empty solution",
            "AI failed to generate a valid puzzle. Please try again.",
        )
    logger.info("Generated solution for topic=%r difficulty=%r: %r", topic_name, difficulty, solution)
    return solution


@dataclass
class AnswerResult:
    answer: str
    explanation: str


async def ask_question(
    client: LLMClient,
    question: str,
    secret_solution: str,
    topic_name: str,
) -> Optional[AnswerResult]:
    """Ask the LLM a question about the secret solution.

    Returns an AnswerResult with the answer and explanation, or None if
    the LLM gave an unparseable response.
    """
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
        solution=secret_solution, topic=topic_name,
    )
    raw_response = await client.ask(system_prompt, question, max_tokens=400)
    lines = raw_response.strip().splitlines()
    if not lines:
        logger.warning("LLM response had no lines after stripping for question=%r", question)
        return None
    answer = lines[-1].strip().lower().rstrip(".")
    if answer not in LEGAL_RESPONSES:
        logger.warning(
            "LLM gave invalid answer=%r for question=%r, full response=%r",
            answer, question, raw_response,
        )
        return None
    explanation = "\n".join(lines[:-1]).strip()
    return AnswerResult(answer=answer, explanation=explanation)


NORMALIZE_TOPIC_PROMPT = """\
You are helping organize topics for a trivia game.

Given a user's suggested topic (which may be in any language, misspelled, \
informal, or vaguely described), return a clean, concise English topic name \
suitable for display.

Examples:
- "la guerra civil española" -> "Spanish Civil War"
- "dinos" -> "Dinosaurs"
- "ww2 pacific" -> "World War II: Pacific Theater"
- "古代ローマ" -> "Ancient Rome"
- "marvel movies and comics" -> "Marvel"

Reply with ONLY the normalized topic name. No quotes, no explanation.\
"""


async def normalize_topic(client: LLMClient, raw_name: str) -> str:
    """Normalize a user-submitted topic name into clean English."""
    response = await client.ask(
        NORMALIZE_TOPIC_PROMPT,
        f"Suggested topic: {raw_name}",
        max_tokens=30,
        temperature=0.0,
    )
    normalized = response.strip().strip('"').strip("'")
    if not normalized:
        logger.error("LLM returned empty normalization for raw_name=%r", raw_name)
        raise LLMError(
            "LLM returned empty topic normalization",
            "AI could not normalize the topic name. Please try a different name.",
        )
    logger.info("Normalized topic %r -> %r", raw_name, normalized)
    return normalized
