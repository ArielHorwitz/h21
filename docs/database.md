# Database

SQLite database managed by `GameDatabase` in `src/h21/db.py`. Uses WAL journal mode and foreign keys.

## Schema

### `topics`
| Column | Type | Notes |
|--------|------|-------|
| `slug` | TEXT PK | URL-friendly identifier, e.g. `western-history` |
| `name` | TEXT | Display name |
| `user_id` | INTEGER | User who suggested the topic (nullable) |

### `daily_puzzles`
| Column | Type | Notes |
|--------|------|-------|
| `date` | TEXT | ISO date |
| `topic_slug` | TEXT FK | References `topics.slug` |
| `difficulty` | TEXT | `easy`, `medium`, or `hard` |
| `solution` | TEXT | The secret answer |
| `hints` | TEXT | JSON array of 5 hint strings |

Composite primary key: `(date, topic_slug, difficulty)`.

### `games`
| Column | Type | Notes |
|--------|------|-------|
| `game_id` | INTEGER PK | Auto-increment |
| `date` | TEXT | ISO date |
| `topic_slug` | TEXT FK | |
| `difficulty` | TEXT | |
| `user_id` | INTEGER | Player (nullable for legacy games) |
| `started_at` | TEXT | UTC ISO timestamp |
| `ended_at` | TEXT | Null while in progress |
| `result` | TEXT | `win`, `loss`, or null |
| `questions_asked` | INTEGER | Counter, updated on each question |

### `questions`
| Column | Type | Notes |
|--------|------|-------|
| `question_id` | INTEGER PK | Auto-increment |
| `game_id` | INTEGER FK | References `games.game_id` |
| `question_number` | INTEGER | 1-based position in the game |
| `question` | TEXT | Player's question text |
| `answer` | TEXT | LLM's one-word answer |
| `explanation` | TEXT | LLM's explanation |
| `asked_at` | TEXT | UTC ISO timestamp |
| `user_id` | INTEGER | Player (nullable) |

### `accounts`
| Column | Type | Notes |
|--------|------|-------|
| `user_id` | INTEGER PK | Auto-increment |
| `username` | TEXT UNIQUE | |
| `password_hash` | TEXT | `salt:sha256_hex` format |
| `role` | TEXT | `user` or `dev` |
| `blocked` | INTEGER | 0 or 1 |
| `daily_question_limit` | INTEGER | Default 105 |
| `daily_topic_limit` | INTEGER | Default 1 |
| `invite_code` | TEXT | Code used to register |
| `created_at` | TEXT | UTC ISO timestamp |

### `invites`
| Column | Type | Notes |
|--------|------|-------|
| `code` | TEXT PK | 8-char hex, uppercase |
| `alias` | TEXT | Optional human-readable label |
| `role` | TEXT | Role granted to registrants |
| `remaining_uses` | INTEGER | Decremented on each registration |
| `created_at` | TEXT | UTC ISO timestamp |

### `daily_usage`
| Column | Type | Notes |
|--------|------|-------|
| `user_id` | INTEGER | |
| `date` | TEXT | ISO date |
| `questions_used` | INTEGER | |
| `topic_suggestions_used` | INTEGER | |

Composite primary key: `(user_id, date)`. Rows created on first use via `INSERT ... ON CONFLICT DO UPDATE`.

## Migrations

Migrations are individual methods on `GameDatabase`, called sequentially in `ensure_schema()`. Each migration checks whether it has already been applied (typically by checking for a column's existence via `PRAGMA table_info`) and is idempotent.

Current migrations in order:
1. `_migrate_add_explanation_column` -- adds `explanation` to `questions`
2. `_migrate_daily_puzzles_composite_key` -- converts `daily_puzzles` from single-key to composite key
3. `_migrate_games_topic_difficulty` -- adds `topic_slug` and `difficulty` to `games`
4. `_migrate_add_hints_column` -- adds `hints` to `daily_puzzles`
5. `_migrate_add_user_id_to_games` -- adds `user_id` to `games`
6. `_migrate_invites_multi_use` -- replaces `used_at`/`used_by` with `remaining_uses`/`alias`
7. `_migrate_add_invite_code_to_accounts` -- adds `invite_code` to `accounts`
8. `_migrate_add_role_columns` -- adds `role` to `accounts` and `invites`
9. `_migrate_add_blocked_column` -- adds `blocked` to `accounts`
10. `_migrate_add_daily_limits` -- adds `daily_question_limit` and `daily_topic_limit` to `accounts`
11. `_migrate_add_user_id_to_topics` -- adds `user_id` to `topics`
12. `_migrate_add_user_id_to_questions` -- adds `user_id` to `questions`

### Adding a New Migration

1. Add a new method `_migrate_<description>(self)` to `GameDatabase`
2. Check idempotency (e.g. check if column already exists before altering)
3. Call the new method at the end of `ensure_schema()`, after existing migrations
4. If adding a column, also add it to the `CREATE TABLE` in `ensure_schema()` so fresh databases get the full schema directly
