# H21

An AI-powered 21 questions trivia game. Players pick a topic (user-submitted or built-in), choose a difficulty, and ask yes/no questions to guess a secret subject. Built with Python/FastAPI backend, vanilla JS frontend, SQLite database, and OpenAI API for game logic.

## Source Layout

| File | Purpose |
|------|---------|
| `src/h21/main.py` | FastAPI app, all route handlers, middleware, CLI entry point |
| `src/h21/db.py` | SQLite database layer, schema, migrations, all data access |
| `src/h21/llm.py` | OpenAI client wrapper, prompt templates, answer parsing |
| `src/h21/auth.py` | HMAC-signed session cookies, token creation/validation |
| `src/h21/config.py` | XDG-compliant config loading (env vars + TOML file) |
| `src/h21/invite.py` | CLI utility to generate invite codes |
| `src/h21/reset.py` | CLI utility to delete database and logs |

## Frontend Layout

| File | Purpose |
|------|---------|
| `static/home.html/js` | Landing page: topic selection, difficulty picker |
| `static/index.html`, `static/game.js` | Main gameplay: Q&A loop, hints, game state |
| `static/login.html/js` | Registration and login |
| `static/account.html/js` | User profile and stats |
| `static/control.html/js` | Dev-only admin panel: SQL queries, account management |
| `static/help.html` | Game rules and instructions |

## Progressive Discovery

Before modifying a module, read the relevant doc in `docs/` for detailed context:

- **`docs/architecture.md`** -- module responsibilities, request flow, auth model, middleware
- **`docs/database.md`** -- full schema, migration pattern, how to add new migrations
- **`docs/api.md`** -- all API endpoints with methods, paths, auth requirements
- **`docs/frontend.md`** -- page inventory, JS patterns, game state flow
- **`docs/development.md`** -- setup, running, Docker, CLI commands, configuration
