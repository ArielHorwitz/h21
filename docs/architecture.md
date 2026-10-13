# Architecture

## Module Responsibilities

- **`main.py`** -- FastAPI application. Defines all routes, request/response models, middleware (auth + cache control), and the app lifespan (initializes LLM client, database, signing secret). Also contains helper functions like `get_or_draw_solution` and `ensure_hints_exist` that coordinate between db and llm.
- **`db.py`** -- All SQLite access. The `GameDatabase` class owns the connection, schema creation, migrations, and every query. No SQL exists outside this file.
- **`llm.py`** -- `OpenAIClient` wraps the async OpenAI SDK. Public functions (`ask_question`, `generate_solution_batch`, `validate_solution_batch`, `generate_hints`, `normalize_topic`) each use a prompt template and parse the response. `LLMError` is the user-facing error type.
- **`auth.py`** -- Stateless session management. Creates HMAC-SHA256 signed tokens containing `{user_id, exp}` as JSON. Tokens are stored in an `h21_session` httponly cookie with 30-day expiry. The signing secret is persisted in the data directory.
- **`avatar.py`** -- AI-generated profile pictures. Uses `AsyncOpenAI.images.generate()` and `images.edit()` for text-to-image and reference-based generation. Pillow handles resizing to 128x128 webp thumbnails. Files stored in `data_dir/avatars/` as `{player_code}_original.png` and `{player_code}.webp`. Supports a pending/confirm flow for user-initiated generation.
- **`config.py`** -- Loads config from `XDG_CONFIG_HOME/h21/config.toml` with env var overrides. Returns a frozen `Config` dataclass with application, data-path, quota, avatar, and secure-cookie settings.

## Request Flow

1. Request hits FastAPI
2. `no_cache_static` middleware sets cache headers on static/page routes
3. `require_auth` middleware checks the session cookie:
   - Public paths (`/login`, `/api/login`, `/api/register`, `/api/open-signups`, `/static/*`) pass through
   - Dev paths (`/control`, `/api/invites`, `/api/accounts`, `/api/query`, `/api/series`, `/api/settings`, `/api/admin` and a few more) require `role == "dev"`
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

## Dates

UTC is the server's canonical time; each player's day follows their own clock. Every page loads `static/tz.js`, which puts the browser's time zone in a `tz` cookie, and `player_today(request)` turns it into the player's date (UTC's when unknown or invalid). Every time zone is within 14 hours of UTC, so a player's date is always UTC's yesterday, today or tomorrow, and two dates can be live at once. The middleware remembers each player's zone on their account, so admin views (`account_today`) use the player's date too.

- **Puzzles** belong to a date and are drawn on demand by the first player to start one on that date.
- **Games carry over.** A game belongs to its puzzle, so a player can finish it on a later day. A series offers the player's open game, from any date, until it ends (`_current_game`); meanwhile the game page says today's puzzle is waiting, and the results page offers it once the game ends. Puzzles of the days in between are skipped. An open game from another day with nothing asked is dropped instead. Results are `win`, `loss` or, rarely, `abandoned` (set by the system or an admin).
- **Usage** is recorded on the player's local date, so quotas reset at their midnight; a question counts against the date it's asked, not its puzzle's. Pictures are summed over the player's local month. A valid clock only reaches three dates at any moment, so changing it gains at most one extra day's quota, once.
- **Spoilers:** a replay is gated while the viewer could still play its puzzle (their today or later, or their own open game) and hasn't finished it.
- Open sign-ups are the exception: they're counted per UTC day.

## Registration

Anyone can join without an invite while the day's open spots last (`open_signups_per_day`, default 3, counted per UTC day; 0 turns it off). Open sign-ups get their own quotas (200 questions and 2 topics a day, 3 pictures a month by default). Invites still work when the spots are gone, and their quotas come from the invite or the config defaults. All four values live in the `settings` table and are edited from the control panel. Picture prompts are recorded in the activity log for review.

So newcomers without friends or an invite still have someone to follow, friend suggestions fill any slots left after followers, friends of friends and invite-mates with players active in the last week (most recent first, never anonymous or blocked ones).

## Key Patterns

- All persistent state is in SQLite (WAL mode, foreign keys enabled). No in-memory caches.
- LLM calls are async. The app uses `AsyncOpenAI`.
- Terms follow `docs/glossary.md`: a **series** is a topic at one difficulty, a **puzzle** is a series' daily instance, a **game** is one player's attempt.
- Puzzles come from a pre-generated pool per series. Each refill generates a batch of 100 solutions in one LLM call and validates them in a second (topic fit, difficulty, duplicates); only kept solutions enter the pool. Every refill is retried once if it errors or keeps too few, and a bad outcome is only believed once the retry agrees.
- `get_or_draw_solution` draws a puzzle on the first request for a date and series (serialized by a per-puzzle lock): the solution leaves the pool and becomes the day's puzzle in one transaction, then its hints are generated. If an available series' pool is unexpectedly empty, it refills on the spot.
- A new topic is built in the background, both difficulties concurrently. Each series with at least 50 solutions becomes `available`, the rest `unavailable`; the topic is `ready` if any series is available and `failed` (with the counts) if none is, or if a difficulty errors twice. A model then sets aside five representative **preview** solutions from the normal pool, shown to players and never drawn. Builds interrupted by a restart resume at startup. There are no built-in topics.
- Series lifecycle: `available` refills in the background below 50 solutions, one refill at a time across the app. A refill keeping fewer than 10 (after its retry) moves the series to `winding_down`; when its last puzzle is drawn it becomes `finished`. A refill erroring twice flags the series (`needs_attention`) for the control panel, where an admin can refill or reopen it.
- Hints are backfilled for a puzzle whose hint generation failed.
- Global in-memory state is limited to in-flight background task bookkeeping and the draw locks.
- Global module-level variables (`llm_client`, `database`, `signing_secret`) are initialized in the lifespan context manager.
