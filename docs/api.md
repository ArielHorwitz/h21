# API Endpoints

All API endpoints are defined in `src/h21/main.py`. JSON request/response bodies use Pydantic models defined at the top of the file.

## Authentication

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/api/register` | Public | Create account with username, password and an optional invite code. Without one, it takes one of the day's open spots (403 when none are left) and gets the open sign-up quotas. Sets session cookie. |
| GET | `/api/open-signups` | Public | `available`: whether someone can join today without an invite. |
| POST | `/api/login` | Public | Authenticate with username/password. Sets session cookie. |
| POST | `/api/logout` | User | Clears session cookie. |
| GET | `/api/me` | User | Returns current user info and daily usage stats. |

## Topics

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/topics` | User | List ready topics, plus the user's own topics still being built. Each has `series` (per difficulty: `state` available/winding_down/finished and `remaining`), `preview` (five solutions), `is_new` and `suggested_by_me`. |
| POST | `/api/topics` | User | Submit a new topic. LLM tidies the name, then the topic is built in the background (status `generating`). Counts against the daily topic limit. 409 if a topic with the same tidied name exists or is being built; a turned-down one may be tried again. |
| GET | `/api/topics/turned-down` | User | Recently turned-down topics with the reason (e.g. how many solutions each difficulty kept). |

## Admin (admin only)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/settings` | Admin | Admin settings (open sign-ups per day and their quotas) and open sign-ups used today. |
| POST | `/api/settings` | Admin | Update settings: `{"values": {key: int}}`. 400 for unknown keys or negative values. |
| GET | `/api/admin/new-topics` | Admin | Ready topics currently tagged New (their first 3 days). |
| DELETE | `/api/admin/new-topics/{slug}` | Admin | Remove a topic's New tag, e.g. from topics seeded at launch. |
| GET | `/api/admin/attention` | Admin | What needs the admin, for the Admin tab badge: pending invite requests, flagged series, whether today's open spots are used up, and their `total`. |

## Series (admin only)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/series` | Admin | Every series with status, pool size, puzzles played, last refill and any attention flag. |
| POST | `/api/series/{topic_slug}/{difficulty}/refill` | Admin | Run a refill now. |
| POST | `/api/series/{topic_slug}/{difficulty}/reopen` | Admin | Make a winding-down or finished series available again and clear its flag. |

## Games

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/game/existing?topic_slug=...&difficulty=...` | User | The game the series offers the user: their open game from any date, else their game on today's puzzle (the player's today). Open games include `new_puzzle_waiting`. Returns 204 if none. |
| GET | `/api/game/statuses` | User | The user's games on today's puzzles, plus open games from other dates (with `date`). |
| POST | `/api/game/new` | User | Start a game on today's puzzle for a ready topic+difficulty, drawing it from the pool if needed. 409 if the series already offers a game, 410 if the series has finished, 503 if the topic has run out of puzzles. |
| POST | `/api/game/end` | User | End a game with result (`win`/`loss`), whatever its date. Returns solution and hints. 409 if already ended. |
| POST | `/api/ask` | User | Ask a question in an open game (`game_id`, `question_number`). LLM judges against the game's puzzle. Counts against today's question limit. 409 if the game has ended. |
| POST | `/api/hint` | User | Get a hint by index (0-4). Requires `(hint_index + 1) * 4` questions asked. |
| GET | `/api/history` | User | Get all past games with questions for the current user. |

## Avatars

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/api/avatar/generate` | User | Generate avatar from prompt and/or reference image (multipart form). Returns base64 preview. |
| POST | `/api/avatar/confirm` | User | Confirm pending avatar as active. |
| POST | `/api/avatar/discard` | User | Discard pending avatar. |
| GET | `/avatars/{player_code}.webp` | Public | Serve avatar thumbnail (128x128 webp). Cache-busted via `?v=` param. |
| GET | `/avatars/{player_code}_original.png` | Public | Serve original avatar (full resolution PNG). |

## Admin (admin role only)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/invites` | Admin | List all invite codes. |
| POST | `/api/invites` | Admin | Create an invite code with optional alias, uses count, and role. |
| DELETE | `/api/invites/{code}` | Admin | Delete an invite code. |
| GET | `/api/accounts` | Admin | List all accounts with daily usage stats. |
| POST | `/api/accounts/{user_id}/block` | Admin | Block an account (cannot block self). |
| POST | `/api/accounts/{user_id}/unblock` | Admin | Unblock an account. |
| POST | `/api/accounts/{user_id}/limits` | Admin | Update daily question and topic limits. |
| POST | `/api/accounts/{user_id}/reset-usage` | Admin | Reset daily usage counters. |
| POST | `/api/query` | Admin | Execute a read-only SQL query against the database. |
| GET | `/api/logs` | Admin | Read log file lines. Query params: `mode` (`head`\|`tail`, default `tail`), `lines` (1-10000, default 100). |

## Page Routes

| Path | File Served |
|------|-------------|
| `/` | `home.html` |
| `/game` | `index.html` |
| `/account` | `account.html` |
| `/help` | `help.html` |
| `/control` | `control.html` (admin only) |
| `/login` | `login.html` |
| `/static/*` | Static file serving |

## Rate Limiting

- Questions: tracked per user per day. Checked against `accounts.daily_question_limit` (default 105).
- Topic suggestions: tracked per user per day. Checked against `accounts.daily_topic_limit` (default 1).
- Avatar generations: tracked per user per month. Checked against `accounts.monthly_avatar_limit` (default 3). Auto-generation on registration does not count.
- Returns HTTP 429 when limits are exceeded.
