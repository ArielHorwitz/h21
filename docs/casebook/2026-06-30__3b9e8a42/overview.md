# Registered accounts with invite codes, replacing PoW

## Summary

Replaced the proof-of-work (PoW) authentication system with registered user
accounts. Registration requires a one-time invite code generated via CLI.

## Changes made

### Removed
- `src/h21/pow.py` — PoW challenge/verify logic
- `static/pow-worker.js` — client-side PoW Web Worker
- `static/settings.html` / `static/settings.js` — old settings page
- `bypass_password` and `pow_difficulty` from config
- All password/PoW checks from frontend (home.js, game.js)
- Password banner UI from home and game pages

### Added
- **`src/h21/auth.py`** — session signing with HMAC-SHA256 cookies (auto-generated
  secret persisted to data dir, 30-day sessions, HttpOnly/SameSite)
- **`src/h21/invite.py`** — CLI entry point (`uv run h21-invite`) prints an
  8-char hex invite code; supports `--alias` and `--uses` flags
- **`accounts` table** — `user_id`, `username`, `password_hash`, `invite_code`,
  `created_at`
- **`invites` table** — `code`, `alias`, `remaining_uses`, `created_at`
- **`user_id` column** on `games` table (migration, nullable for old games)
- **`/login` page** (`login.html` / `login.js`) — combined login + registration
  form (registration requires invite code)
- **`/account` page** (`account.html` / `account.js`) — shows username + logout
  button, replaces old settings page
- **API endpoints:** `POST /api/register`, `POST /api/login`, `POST /api/logout`,
  `GET /api/me`
- **Auth middleware** — all routes except `/login`, `/api/login`, `/api/register`,
  and `/static/*` require a valid session cookie; unauthenticated page requests
  redirect to `/login`, unauthenticated API requests return 401

### Modified
- `main.py` — complete rework removing PoW, adding auth middleware and endpoints,
  wiring `user_id` through game creation and history
- `config.py` — removed `pow_difficulty` and `bypass_password` fields
- `db.py` — added account/invite tables, migrations, methods; `create_game`
  accepts `user_id`; `get_history` filters by `user_id`
- `home.js` — simplified, no password checks
- `game.js` — simplified, direct question submission without PoW
- `pyproject.toml` — added `h21-invite` script entry point
- All HTML pages — nav bar links updated from `/settings` to `/account`
- `style.css` — removed password banner / disabled link styles, added auth/account
  page styles

### User identity tracking (follow-up)

Audited all tables and endpoints to ensure every user action is attributed.

- **`user_id` column added to `topics` table** — tracks who suggested each topic
  (migration, nullable for pre-existing topics)
- **`user_id` column added to `questions` table** — direct attribution on each
  question, avoiding the need to join through `games` (migration, nullable for
  pre-existing questions)
- **Game ownership verification** added to `/api/game/end`, `/api/ask`, and
  `/api/hint` — endpoints now return 403 if the authenticated user doesn't own
  the game (legacy games with `user_id = NULL` are exempt)
- **`get_game()` updated** to include `user_id` in its SELECT so ownership
  checks have the data they need

### Game resume on page refresh (follow-up)

Previously, refreshing the game page lost all progress and started a new game.
Now the client checks for an existing in-progress game before creating one.

- **`get_active_game()` in `db.py`** — finds the user's unfinished game for a
  given date+topic+difficulty and returns it with its full question history
- **`GET /api/game/active`** endpoint — returns the active game or 204 if none
- **`game.js` updated** — `init()` calls `/api/game/active` first; if a game
  exists, it restores `gameId`, `questionsAsked`, `answerHistory`, the question
  log, and the hint panel; only creates a new game if no active game is found

## Design decisions

- **Signed cookies** over session table — simplest approach, no session revocation
  needed for this scale
- **Auto-generated signing secret** stored in data dir — zero config burden,
  survives restarts
- **Password hashing** — SHA-256 with random salt (adequate for invite-only app
  with few users)
- **Invite codes** — 8-char uppercase hex, generated via CLI with optional alias
  and configurable use count (default 1); accounts record which invite was used
- Old games (pre-accounts) become orphaned with `user_id = NULL` — acceptable

### Invite-level default limits (follow-up)

Previously, all new accounts received hardcoded default limits (105 questions,
1 topic suggestion per day) regardless of which invite code was used. Admins had
to manually adjust limits per-account after registration.

- **`daily_question_limit` and `daily_topic_limit` columns added to `invites`
  table** — nullable integers; NULL means "use account defaults" (105/1)
- **`consume_invite()` updated** to return a dict with `role`,
  `daily_question_limit`, and `daily_topic_limit` (previously returned just the
  role string)
- **`create_account()` updated** to accept optional limit overrides, applied when
  the invite specifies non-NULL values
- **Registration endpoint** passes invite limits through to account creation
- **CLI** (`h21-invite`) — added `--question-limit` and `--topic-limit` flags
- **API** (`POST /api/invites`) — added `daily_question_limit` and
  `daily_topic_limit` fields to the request body
- **Control panel** — invite creation form includes limit fields; invites table
  shows a "Limits" column displaying `Q: N / T: N` or "default"
