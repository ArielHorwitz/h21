# Architecture

## Module Responsibilities

- **`main.py`** -- FastAPI application. Defines all routes, request/response models, middleware (auth + cache control), and the app lifespan (initializes LLM client, database, signing secret). Also contains helper functions like `get_today_solution` and `ensure_hints_exist` that coordinate between db and llm.
- **`db.py`** -- All SQLite access. The `GameDatabase` class owns the connection, schema creation, migrations, and every query. No SQL exists outside this file.
- **`llm.py`** -- `OpenAIClient` wraps the async OpenAI SDK. Public functions (`ask_question`, `generate_solution_batch`, `validate_solution_batch`, `generate_hints`, `normalize_topic`) each use a prompt template and parse the response. `LLMError` is the user-facing error type.
- **`auth.py`** -- Stateless session management. Creates HMAC-SHA256 signed tokens containing `{user_id, exp}` as JSON. Tokens are stored in an `h21_session` httponly cookie with 30-day expiry. The signing secret is persisted in the data directory.
- **`avatar.py`** -- AI-generated profile pictures. Uses `AsyncOpenAI.images.generate()` and `images.edit()` for text-to-image and reference-based generation. Pillow handles resizing to 128x128 webp thumbnails. Files stored in `data_dir/avatars/` as `{player_code}_original.png` and `{player_code}.webp`. Supports a pending/confirm flow for user-initiated generation.
- **`config.py`** -- Loads config from `XDG_CONFIG_HOME/h21/config.toml` with env var overrides. Returns a frozen `Config` dataclass with application, data-path, quota, avatar, and secure-cookie settings.

## Request Flow

1. Request hits FastAPI
2. `no_cache_static` middleware sets cache headers on static/page routes
3. `require_auth` middleware checks the session cookie:
   - Public paths (`/login`, `/api/login`, `/api/register`, `/static/*`) pass through
   - Dev paths (`/control`, `/api/invites`, `/api/accounts`, `/api/query`) require `role == "dev"`
   - All other paths require a valid, non-blocked account
   - Sets `request.state.user_id` and `request.state.role` for downstream handlers
4. Route handler executes, typically calling `database.*` and/or `llm_client` via helper functions
5. Response returned as JSON (API) or HTML (pages). Page routes go through
   `render_page`, which reads the static HTML file and resolves the
   `__BASE_URL__` placeholder (used by Open Graph tags, which need absolute
   URLs) from the request's `Host`/`X-Forwarded-Proto` headers.

## Auth Model

- **Registration** requires a valid invite code. The invite's `role` determines the new account's role.
- **Login** returns a signed session cookie. No server-side session store.
- **Cookie transport** is configurable: local HTTP development defaults to a
  non-secure cookie, while HTTPS deployments set `secure_cookies = true`.
- **Roles**: `user` (standard access) and `dev` (admin panel, SQL queries, account/invite management).
- **Blocking**: Accounts can be blocked by devs. Blocked accounts are rejected at the middleware level.

## Rate Limiting

Per-user daily quotas tracked in `daily_usage` table:
- `daily_question_limit` (default 105) -- max questions per day across all games
- `daily_topic_limit` (default 1) -- max topic suggestions per day
- Devs can reset usage or adjust limits per account

## Key Patterns

- All persistent state is in SQLite (WAL mode, foreign keys enabled). No in-memory caches.
- LLM calls are async. The app uses `AsyncOpenAI`.
- Puzzles come from a pre-generated pool per topic and difficulty. Each refill generates a batch of 100 subjects in one LLM call and validates them in a second (topic fit, difficulty, duplicates); only kept subjects enter the pool. `get_today_solution` draws one at random on the first request for a date/topic/difficulty (serialized by a per-puzzle lock), generates its hints, and persists it.
- A new topic is built in the background: both difficulty pools are filled, and the topic becomes `ready`, or `failed` if either pool kept fewer than 50 subjects. Builds interrupted by a restart, and the seeded default topics, are built at startup.
- A pool is refilled in the background once it drops below 50 subjects. If a refill keeps fewer than 10, the pool is treated as exhausted and not refilled again; when it empties, the topic answers 503.
- Hints are backfilled for a puzzle whose hint generation failed.
- Global in-memory state is limited to in-flight background task bookkeeping and the draw locks.
- Global module-level variables (`llm_client`, `database`, `signing_secret`) are initialized in the lifespan context manager.
