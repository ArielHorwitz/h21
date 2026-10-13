# H21

An AI-powered 21 questions trivia game. Players pick a topic (suggested by players), choose a difficulty, and ask yes/no questions to guess a secret solution. Built with Python/FastAPI backend, vanilla JS frontend, SQLite database, and OpenAI API for game logic.

## Source Layout

| File | Purpose |
|------|---------|
| `src/h21/main.py` | FastAPI app, all route handlers, middleware, CLI entry point |
| `src/h21/db.py` | SQLite database layer, schema, all data access |
| `src/h21/llm.py` | OpenAI client wrapper, prompt templates, answer parsing |
| `src/h21/auth.py` | HMAC-signed session cookies, token creation/validation |
| `src/h21/config.py` | XDG-compliant config loading (env vars + TOML file) |
| `src/h21/avatar.py` | AI-generated profile pictures: OpenAI image API, Pillow resize, file management |
| `src/h21/invite.py` | CLI utility to generate invite codes |
| `src/h21/reset.py` | CLI utility to delete database and logs |
| `src/h21/sandbox.py` | CLI utility to create/run a seeded local sandbox instance for testing |
| `src/h21/generate.py` | `h21-pool` CLI to evaluate puzzle generation and validation prompts |

## Frontend Layout

| File | Purpose |
|------|---------|
| `static/home.html/js` | Today: topic list with per-difficulty play buttons |
| `static/suggest.html/js` | Suggest a topic: form with quota, your topics |
| `static/index.html`, `static/game.js` | Main gameplay: Q&A loop, hints, game state |
| `static/replay.html/js` | Game results and replays |
| `static/friends.html/js` | Recent games with friends, search, suggestions, people links, privacy |
| `static/people.html/js` | Following, Followers and Suggested lists |
| `static/people-list.js` | Person rows and follow actions shared by Friends and People |
| `static/leaderboard.html/js` | Per-puzzle leaderboard |
| `static/login.html/js` | Log in, join (invite optional while open spots last), invite requests |
| `static/account.html/js` | Profile: picture, name, stats, history, settings |
| `static/control.html/js` | Dev-only admin panel: SQL queries, account management |
| `static/help.html` | Game rules and instructions |
| `static/partials/*.html` | Shared top bar and tab bar, included by `render_page` |
| `static/question-log.js` | Question log rendering shared by game and results |
| `static/nav.js` | Shared script: Profile tab avatar, Admin tab and its badge for devs |

## Progressive Discovery

Before modifying a module, read the relevant doc in `docs/` for detailed context:

- **`docs/glossary.md`** -- the terms topic, series, puzzle, game, solution, answer, pool; use them in code, copy and docs
- **`docs/architecture.md`** -- module responsibilities, request flow, auth model, middleware
- **`docs/database.md`** -- full schema, how schema changes work
- **`docs/api.md`** -- all API endpoints with methods, paths, auth requirements
- **`docs/frontend.md`** -- page inventory, JS patterns, game state flow
- **`docs/development.md`** -- setup, running, CLI commands, configuration
