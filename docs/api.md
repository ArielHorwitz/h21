# API Endpoints

All API endpoints are defined in `src/h21/main.py`. JSON request/response bodies use Pydantic models defined at the top of the file.

## Authentication

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/api/register` | Public | Create account with username, password, invite code. Sets session cookie. |
| POST | `/api/login` | Public | Authenticate with username/password. Sets session cookie. |
| POST | `/api/logout` | User | Clears session cookie. |
| GET | `/api/me` | User | Returns current user info and daily usage stats. |

## Topics

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/topics` | User | List all topics (slug + name). |
| POST | `/api/topics` | User | Submit a new topic. LLM normalizes the name. Counts against daily topic limit. |

## Games

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/game/existing?topic_slug=...&difficulty=...` | User | Get user's existing game for today's puzzle. Returns 204 if none. |
| POST | `/api/game/new` | User | Start a new game for a topic+difficulty. Generates today's solution if needed. 409 if game already exists. |
| POST | `/api/game/end` | User | End a game with result (`win`/`loss`). Returns solution and hints. |
| POST | `/api/ask` | User | Ask a question. LLM judges against secret solution. Counts against daily question limit. Records Q&A if game_id provided. |
| POST | `/api/hint` | User | Get a hint by index (0-4). Requires `(hint_index + 1) * 4` questions asked. |
| GET | `/api/history` | User | Get all past games with questions for the current user. |

## Admin (dev role only)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/invites` | Dev | List all invite codes. |
| POST | `/api/invites` | Dev | Create an invite code with optional alias, uses count, and role. |
| DELETE | `/api/invites/{code}` | Dev | Delete an invite code. |
| GET | `/api/accounts` | Dev | List all accounts with daily usage stats. |
| POST | `/api/accounts/{user_id}/block` | Dev | Block an account (cannot block self). |
| POST | `/api/accounts/{user_id}/unblock` | Dev | Unblock an account. |
| POST | `/api/accounts/{user_id}/limits` | Dev | Update daily question and topic limits. |
| POST | `/api/accounts/{user_id}/reset-usage` | Dev | Reset daily usage counters. |
| POST | `/api/query` | Dev | Execute a read-only SQL query against the database. |

## Page Routes

| Path | File Served |
|------|-------------|
| `/` | `home.html` |
| `/game` | `index.html` |
| `/account` | `account.html` |
| `/help` | `help.html` |
| `/control` | `control.html` (dev only) |
| `/login` | `login.html` |
| `/static/*` | Static file serving |

## Rate Limiting

- Questions: tracked per user per day. Checked against `accounts.daily_question_limit` (default 105).
- Topic suggestions: tracked per user per day. Checked against `accounts.daily_topic_limit` (default 1).
- Returns HTTP 429 when limits are exceeded.
