# Database

SQLite database managed by `GameDatabase` in `src/h21/db.py`. Uses WAL journal mode and foreign keys.

## Schema

### `topics`
| Column | Type | Notes |
|--------|------|-------|
| `slug` | TEXT PK | URL-friendly identifier, e.g. `western-history` |
| `name` | TEXT | Display name |
| `user_id` | INTEGER | User who suggested the topic (nullable) |
| `status` | TEXT | `generating`, `ready`, or `failed` |
| `status_detail` | TEXT | User-facing reason when `failed` (nullable) |
| `created_at` | TEXT | UTC ISO timestamp |

### `series`
| Column | Type | Notes |
|--------|------|-------|
| `topic_slug` | TEXT FK | |
| `difficulty` | TEXT | `normal` or `expert` |
| `status` | TEXT | `available`, `winding_down`, `finished`, or `unavailable` (too few solutions when built) |
| `needs_attention` | TEXT | Why the admin should look (e.g. a refill failed twice), or NULL |

Primary key `(topic_slug, difficulty)`. Created when a topic is built.

### `preview_solutions`
| Column | Type | Notes |
|--------|------|-------|
| `topic_slug` | TEXT FK | |
| `position` | INTEGER | 0 to 4 |
| `solution` | TEXT | A representative solution shown to players; never drawn as a puzzle and excluded from future batches |

### `pool_solutions`
| Column | Type | Notes |
|--------|------|-------|
| `pool_id` | INTEGER PK | Auto-increment |
| `topic_slug` | TEXT FK | References `topics.slug` |
| `difficulty` | TEXT | `normal` or `expert` |
| `solution` | TEXT | A validated, undrawn solution |
| `generated_at` | TEXT | UTC ISO timestamp |

Unique on `(topic_slug, difficulty, solution)`. Drawing a solution deletes its row and records it in `puzzles`.

### `pool_refills`
| Column | Type | Notes |
|--------|------|-------|
| `refill_id` | INTEGER PK | Auto-increment |
| `topic_slug` | TEXT FK | |
| `difficulty` | TEXT | |
| `generated` | INTEGER | Solutions the generation call returned |
| `kept` | INTEGER | Solutions that passed validation and entered the pool |
| `finished_at` | TEXT | UTC ISO timestamp |

One row per successful refill. The latest row's `kept` drives the exhaustion guard.

### `puzzles`
| Column | Type | Notes |
|--------|------|-------|
| `date` | TEXT | ISO date |
| `topic_slug` | TEXT FK | References `topics.slug` |
| `difficulty` | TEXT | `normal` or `expert` |
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
| `user_id` | INTEGER | Player |
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
| `invite_code` | TEXT | Code used to register; NULL for an open sign-up |
| `avatar_version` | INTEGER | Bumped on each avatar change (0 = no avatar) |
| `avatar_generations_used` | INTEGER | Monthly counter for avatar generations |
| `avatar_generation_reset` | TEXT | ISO date of last counter reset (nullable) |
| `monthly_avatar_limit` | INTEGER | Max avatar generations per month (default 3) |
| `created_at` | TEXT | UTC ISO timestamp |

### `invites`
| Column | Type | Notes |
|--------|------|-------|
| `code` | TEXT PK | 8-char hex, uppercase |
| `alias` | TEXT | Optional human-readable label |
| `role` | TEXT | Role granted to registrants |
| `remaining_uses` | INTEGER | Decremented on each registration |
| `daily_question_limit` | INTEGER | Default question limit for registrants (nullable, NULL = 105) |
| `daily_topic_limit` | INTEGER | Default topic limit for registrants (nullable, NULL = 1) |
| `monthly_avatar_limit` | INTEGER | Default avatar generation limit for registrants (nullable, NULL = 3) |
| `created_at` | TEXT | UTC ISO timestamp |

### `settings`
| Column | Type | Notes |
|--------|------|-------|
| `key` | TEXT PK | One of `SETTING_DEFAULTS` in `db.py` |
| `value` | INTEGER | |

Admin-editable values. A missing row means the default applies.

### `daily_usage`
| Column | Type | Notes |
|--------|------|-------|
| `user_id` | INTEGER | |
| `date` | TEXT | ISO date |
| `questions_used` | INTEGER | |
| `topic_suggestions_used` | INTEGER | |

Composite primary key: `(user_id, date)`. Rows created on first use via `INSERT ... ON CONFLICT DO UPDATE`.

## Schema changes

There are no migrations. `ensure_schema()` creates every table with `CREATE TABLE IF NOT EXISTS`, and the schema was consolidated for the relaunch, so databases from before it are not supported. To change the schema, edit the `CREATE TABLE` statements and recreate the database (`h21-reset`). If production data ever needs preserving across a schema change, reintroduce a migration step then.
