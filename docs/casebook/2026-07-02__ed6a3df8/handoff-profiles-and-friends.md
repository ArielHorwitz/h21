# Handoff: Profiles & Friends

Phase 1 of the social comparison feature. Adds player codes, display names,
anonymous mode, and a unidirectional friends system.

## Database Changes (`src/h21/db.py`)

### New columns on `accounts`

| Column | Type | Default | Notes |
|--------|------|---------|-------|
| `display_name` | TEXT | NULL | Editable. When NULL, UI falls back to `username`. |
| `player_code` | TEXT UNIQUE | — | Generated at creation. Short hex string (start at 4 chars). Immutable. |
| `anonymous` | INTEGER | 0 | Full social opt-out. When 1: others cannot see this player (search, lookup, friends lists, comparisons), AND this player cannot see others (friends list returns empty, search/lookup disabled). Friend rows are preserved so toggling off restores everything. |

### New table: `friends`

```sql
CREATE TABLE IF NOT EXISTS friends (
    user_id    INTEGER NOT NULL,
    friend_id  INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (user_id, friend_id),
    FOREIGN KEY (user_id) REFERENCES accounts(user_id),
    FOREIGN KEY (friend_id) REFERENCES accounts(user_id)
);
```

Unidirectional: a row `(A, B)` means "A follows B." No mutual confirmation.

### Migrations

Two new migrations, called at the end of `ensure_schema()`:

1. **`_migrate_add_profile_columns`** — adds `display_name`, `player_code`,
   `anonymous` to `accounts`. After adding `player_code`, backfills existing
   accounts that have NULL player codes.

2. **`_migrate_add_friends_table`** — creates the `friends` table.

#### Player code generation

Generate codes starting at 4 hex chars (`secrets.token_hex(2).upper()`). On
collision (UNIQUE constraint violation), retry. If too many retries (e.g. 10),
bump length to 5 chars. This is only relevant during backfill of existing
accounts; new accounts go through `create_account` which does the same.

### Modified methods

**`create_account`**: generate and store a `player_code` alongside the other
fields. Add it to the INSERT statement.

**`get_account_by_id`**: add `display_name`, `player_code`, `anonymous` to the
SELECT.

**`get_account_by_username`**: add `player_code` to the SELECT (needed if we
ever want to show it at login).

**`get_all_accounts`**: add the new columns to the SELECT (admin panel
visibility).

### New methods

```python
def update_profile(self, user_id: int, display_name: Optional[str],
                   anonymous: bool) -> bool:
    """Update display_name and anonymous flag. Returns True if the row was
    updated."""

def get_account_by_player_code(self, player_code: str) -> Optional[dict]:
    """Look up an account by player_code. Returns None if not found."""

def search_players(self, query: str, exclude_user_id: int) -> list[dict]:
    """Search non-anonymous accounts by username or display_name (LIKE
    match). Excludes the searching user. Excludes anonymous players.
    Returns list of {user_id, username, display_name, player_code}."""

def add_friend(self, user_id: int, friend_id: int) -> bool:
    """Add a follow relationship. Returns True if created, False if already
    exists. Should not allow self-follows (user_id == friend_id).
    Does NOT check anonymous — the relationship is stored regardless."""

def remove_friend(self, user_id: int, friend_id: int) -> bool:
    """Remove a follow relationship. Returns True if a row was deleted."""

def get_friends(self, user_id: int) -> list[dict]:
    """Return all friends (accounts the user follows). Each entry includes
    user_id, username, display_name, player_code, anonymous.
    Does NOT filter by anonymous — returns all friend rows. The API layer
    gates access: if the requesting user is anonymous, the endpoint
    returns an empty list; otherwise, anonymous friends are still returned
    (with the flag set) so the UI can show them as unavailable."""
```

## API Changes (`src/h21/main.py`)

### Modified endpoints

**`GET /api/me`** — add `display_name`, `player_code`, `anonymous` to the
response dict.

### New endpoints

#### `PATCH /api/me`

Update profile fields.

```
Request:  { "display_name": "Alice" | null, "anonymous": true | false }
Response: { "status": "ok" }
```

Both fields optional — only update what's provided. Validate `display_name`
length (1-40 chars if not null, stripped of whitespace).

#### `GET /api/players/search?q=...`

Search for non-anonymous players by name.

```
Response: [{ "username": "...", "display_name": "...", "player_code": "..." }, ...]
```

Requires the query to be at least 1 character. Limit results to 20. Excludes
the requesting user. Excludes anonymous players. Returns 403 if the requesting
user is anonymous.

#### `GET /api/players/{player_code}`

Look up a player by their code.

```
Response: { "username": "...", "display_name": "...", "player_code": "..." }
```

Returns 404 if not found or if the target player is anonymous. Returns 403 if
the requesting user is anonymous.

#### `GET /api/friends`

List the current user's friends.

```
Response: [{ "username": "...", "display_name": "...", "player_code": "...",
             "anonymous": true | false }, ...]
```

If the requesting user is anonymous, returns an empty list (social features
disabled). Otherwise, returns all friends including anonymous ones — the
`anonymous` flag lets the UI indicate "this friend has gone anonymous" rather
than silently dropping them.

#### `POST /api/friends/{player_code}`

Follow a player.

```
Response: { "status": "ok" }
```

Returns 404 if the player_code doesn't exist. Returns 400 if trying to follow
self. Returns 409 if already following. Returns 403 if the requesting user is
anonymous. Does NOT check the target's anonymous flag — the relationship is
stored regardless, it's just dormant while either party is anonymous.

#### `DELETE /api/friends/{player_code}`

Unfollow a player.

```
Response: { "status": "ok" }
```

Returns 404 if the player_code doesn't exist or the relationship doesn't exist.
This endpoint works even if the requesting user is anonymous (you can always
remove your own follow relationships).

### Auth middleware

All new endpoints require standard user auth (same as existing game endpoints).
No dev-only restrictions. Add the new paths to the middleware allowlist if
needed.

## Frontend Changes (`static/account.html`, `static/account.js`)

### Profile section (modify existing)

Below the existing username display, add:

- **Display name** — editable text field with a save button. Pre-populated from
  `/api/me`. Saving calls `PATCH /api/me`.
- **Player code** — read-only, displayed prominently with a "copy" button.
- **Anonymous toggle** — checkbox or toggle switch. Saving calls `PATCH /api/me`.

### Friends section (new)

Below the profile section, add a friends management area:

- **Add friend** — text input for player code + "Add" button. Calls
  `POST /api/friends/{code}`.
- **Search** — text input that searches on keyup (debounced). Calls
  `GET /api/players/search?q=...`. Each result shows display name (or
  username), player code, and a "Follow" button.
- **Friends list** — fetched from `GET /api/friends`. Each entry shows display
  name (or username), player code, anonymous badge if applicable, and a
  "Remove" button.

When the user is anonymous, the friends section should be visually disabled or
hidden, with a message like "Social features are disabled while anonymous mode
is on." The anonymous toggle in the profile section above controls this — when
toggled on, the friends section greys out or collapses; when toggled off, it
becomes interactive again.

### Style notes

Follow the existing pattern: vanilla JS, no framework. Use the existing CSS
classes and layout conventions from `style.css`. The account page currently uses
`.auth-section`, `.settings-field`, `.settings-actions` — reuse those.

## Testing Considerations

- Player code uniqueness under concurrent account creation.
- Anonymous player excluded from search results.
- Anonymous player excluded from player lookup by code.
- Anonymous player's friends list returns empty.
- Anonymous player cannot search, look up players, or follow (403).
- Anonymous player CAN unfollow (DELETE always works).
- Anonymous player's games not visible via future recap endpoints (verify the
  flag is checked).
- Following a non-anonymous player while non-anonymous succeeds normally.
- Friend rows preserved when a player toggles anonymous on then off.
- Self-follow returns 400.
- Display name validation: null allowed, empty string after strip treated as
  null, max 40 chars.
- Backfill migration: all existing accounts get player codes, no duplicates.

## What This Does NOT Include

- Profile pictures (deferred — separate feature).
- Daily recap / comparison (Phase 2, depends on this).
- Comparison page (Phase 3).
- Any changes to the game flow or home page.
