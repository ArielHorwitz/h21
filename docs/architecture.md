# Architecture

## Module Responsibilities

- **`main.py`** -- FastAPI application. Defines all routes, request/response models, middleware (auth + cache control), and the app lifespan (initializes LLM client, database, signing secret). Also contains helper functions like `get_today_solution` and `ensure_hints_exist` that coordinate between db and llm.
- **`db.py`** -- All SQLite access. The `GameDatabase` class owns the connection, schema creation, migrations, and every query. No SQL exists outside this file.
- **`llm.py`** -- `OpenAIClient` wraps the async OpenAI SDK. Four public functions (`ask_question`, `generate_solution`, `generate_hints`, `normalize_topic`) each use a prompt template and parse the response. `LLMError` is the user-facing error type.
- **`auth.py`** -- Stateless session management. Creates HMAC-SHA256 signed tokens containing `{user_id, exp}` as JSON. Tokens are stored in an `h21_session` httponly cookie with 30-day expiry. The signing secret is persisted in the data directory.
- **`config.py`** -- Loads config from `XDG_CONFIG_HOME/h21/config.toml` with env var overrides. Returns a frozen `Config` dataclass with `openai_api_key`, `model`, `reasoning_effort`, `db_path`, `log_path`.

## Request Flow

1. Request hits FastAPI
2. `no_cache_static` middleware sets cache headers on static/page routes
3. `require_auth` middleware checks the session cookie:
   - Public paths (`/login`, `/api/login`, `/api/register`, `/static/*`) pass through
   - Dev paths (`/control`, `/api/invites`, `/api/accounts`, `/api/query`) require `role == "dev"`
   - All other paths require a valid, non-blocked account
   - Sets `request.state.user_id` and `request.state.role` for downstream handlers
4. Route handler executes, typically calling `database.*` and/or `llm_client` via helper functions
5. Response returned as JSON (API) or FileResponse (pages)

## Auth Model

- **Registration** requires a valid invite code. The invite's `role` determines the new account's role.
- **Login** returns a signed session cookie. No server-side session store.
- **Roles**: `user` (standard access) and `dev` (admin panel, SQL queries, account/invite management).
- **Blocking**: Accounts can be blocked by devs. Blocked accounts are rejected at the middleware level.

## Rate Limiting

Per-user daily quotas tracked in `daily_usage` table:
- `daily_question_limit` (default 105) -- max questions per day across all games
- `daily_topic_limit` (default 1) -- max topic suggestions per day
- Devs can reset usage or adjust limits per account

## Key Patterns

- All state is in SQLite (WAL mode, foreign keys enabled). No in-memory caches.
- LLM calls are async. The app uses `AsyncOpenAI`.
- Daily puzzles are generated lazily: `get_today_solution` generates and persists the solution+hints on first request for a given date/topic/difficulty combination.
- Hints are backfilled for older puzzles that predate the hints feature.
- Global module-level variables (`llm_client`, `database`, `signing_secret`) are initialized in the lifespan context manager.
