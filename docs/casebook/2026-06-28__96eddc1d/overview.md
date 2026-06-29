# H21 — History-themed 21 Questions

## Vision

H21 is a daily history trivia game in the style of Wordle. Each day, there is a
single historical subject (a person, event, or place). Players ask up to 21
yes/no questions to identify it. An LLM answers each question, but its responses
are programmatically validated — the raw LLM output never reaches the player.

The game is deployed on a minimal VPS for a small group of friends. No
authentication, no accounts — the honor system. A proof-of-work mechanism
prevents LLM API abuse.

## Key decisions

- **Subject domain**: mainstream western history, prehistoric to modern day —
  figures, events, and places.
- **Daily puzzle**: one answer per day, drawn sequentially from a user-curated
  list (`daily-solutions.txt`, one entry per line). Index is
  `(today - start_date).days % len(solutions)`, wrapping when the list is
  exhausted.
- **LLM as oracle only**: the LLM receives the player's question and the secret
  answer via a system prompt. Its response is parsed for exactly one of:
  `yes`, `no`, `partially`, `depends`, `win`. Anything else is an error. This
  prevents prompt injection, answer leakage, and off-script behavior.
- **No session tracking**: 21-question limit enforced client-side. No cookies,
  no login. Friends can "cheat" if they want to.
- **Proof of work**: client-side SHA-256 PoW before each question. Tunable
  difficulty. Cheap to verify server-side, expensive to spam.
- **Stack**: Python + FastAPI + vanilla HTML/JS. SQLite not needed yet (no
  persistence). Single-container Docker deployment.
- **LLM provider**: OpenAI initially, behind an abstraction layer for future
  swapability.
