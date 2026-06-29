from __future__ import annotations

from typing import Optional, Protocol

from openai import AsyncOpenAI

LEGAL_RESPONSES = frozenset({"yes", "no", "partially", "depends", "win"})

SYSTEM_PROMPT_TEMPLATE = """\
You are the host of a game of 21 questions. The secret solution is: "{solution}".
The solution is a historical figure, event, or place.

The player will ask you questions or make guesses. You must respond with EXACTLY
one word — one of: yes, no, partially, depends, win.

- "yes" if the answer to their question is clearly yes.
- "no" if the answer is clearly no.
- "partially" if the answer is partly correct or context-dependent.
- "depends" if the answer varies based on interpretation or framing.
- "win" ONLY if the player has correctly identified the secret solution.

Do not reveal the solution. Do not explain. Respond with a single word only.\
"""


class LLMClient(Protocol):
    async def ask(self, system_prompt: str, user_message: str) -> str: ...


class OpenAIClient:
    def __init__(self, api_key: str) -> None:
        self._client = AsyncOpenAI(api_key=api_key)

    async def ask(self, system_prompt: str, user_message: str) -> str:
        response = await self._client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            max_tokens=10,
            temperature=0.0,
        )
        return response.choices[0].message.content or ""


async def ask_question(
    client: LLMClient, question: str, secret_solution: str
) -> Optional[str]:
    """Ask the LLM a question about the secret solution.

    Returns one of the legal responses, or None if the LLM gave an
    unparseable response.
    """
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(solution=secret_solution)
    raw_response = await client.ask(system_prompt, question)
    parsed = raw_response.strip().lower().rstrip(".")
    if parsed in LEGAL_RESPONSES:
        return parsed
    return None
