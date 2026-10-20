# H21

![H21 banner](static/brand/h21-banner.svg)

An AI-powered 21 questions trivia game. Players pick a topic (suggested by
players), choose a difficulty, and ask yes/no questions to guess a secret
solution. Python/FastAPI backend, vanilla JS frontend, SQLite database, OpenAI
API for game logic.

## Quick start

Requires Python 3.12+, [uv](https://docs.astral.sh/uv/), and an OpenAI API key.

```bash
export OPENAI_API_KEY=sk-...
uv sync
uv run h21-invite --role admin   # an invite code for your admin account
uv run h21          # serve on http://127.0.0.1:8000
```

Configuration, CLI commands, and deployment notes:
[docs/development.md](docs/development.md). Architecture, database, API, and
frontend documentation: [docs/](docs/).
