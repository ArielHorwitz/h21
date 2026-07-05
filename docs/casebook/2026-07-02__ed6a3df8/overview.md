# Daily Recap & Social Comparison — Overview

## Problem

A leaderboard was the most requested feature but doesn't fit H21: the player
base is small (~10, friends/family), topics are user-generated and fragmented
across difficulties, and global rankings are easily gamed. See `intro.md` for
the full analysis.

## Solution: Direct Contextual Comparison

Instead of a leaderboard, players see a **daily recap** of yesterday's games
with friend comparisons. "Yesterday" is the anchor so everyone gets the same
experience regardless of play time.

## MVP Scope (phased)

### Phase 1 — Social Infrastructure (profiles + friends)

Build the social foundation that all comparison features depend on:

- **Player codes**: short, public-facing identifiers (start at 4 hex chars,
  grow on exhaustion). Distinct from internal `user_id`. Generated at account
  creation, immutable.
- **Display names**: editable, nullable (falls back to username when null).
- **Anonymous mode**: a full social opt-out. When on, the player is invisible
  to everyone (search, lookup, friends lists, comparisons) — even existing
  followers — AND the player themselves cannot see others (friends list returns
  empty, search/lookup/follow disabled). Friend relationships are preserved
  (not deleted), so toggling anonymous off restores everything in both
  directions.
- **Friends**: unidirectional follow model. "I follow you" means I see your
  results. No mutual confirmation required. Stored as `(user_id, friend_id)`
  rows.
- **Player search/discovery**: search by display name or username (excludes
  anonymous players). Look up by player code.
- **Profile pictures**: deferred. Important for social identity but adds file
  storage, upload UI, serving, and resizing — not MVP.

### Phase 2 — Daily Recap

- Shown on the home page.
- For each game the player played yesterday: show topic, difficulty, date, and
  up to 3 friends who played the same game (top performer + 2 closest scores).
- Ranking: sort by hints first (each hint is a large penalty), then by question
  count. Players see question count and hint count, never a raw score.

### Phase 3 — Comparison Page (deferred)

- Dedicated page per game showing all friends who played, sorted by performance.
- Linked from the recap.

### Deferred Ideas

- Live "today" comparison (asymmetric, ship recap first)
- Friend-driven game discovery ("friends also played these")
- Personal trajectory, head-to-head rivalry, skill profiles
- Category-based recognition

## Implementation Status

### Phase 1 — Complete

All components implemented and tested:

**Database** (`src/h21/db.py`):
- New columns on `accounts`: `display_name`, `player_code`, `anonymous`
- New `friends` table with `(user_id, friend_id)` primary key
- Two migrations (`_migrate_add_profile_columns`, `_migrate_add_friends_table`)
  with player code backfill for existing accounts
- Six new methods: `update_profile`, `get_account_by_player_code`,
  `search_players`, `add_friend`, `remove_friend`, `get_friends`
- Four modified methods: `create_account` (generates player code),
  `get_account_by_id`, `get_account_by_username`, `get_all_accounts`

**API** (`src/h21/main.py`):
- `GET /api/me` extended with `display_name`, `player_code`, `anonymous`
- `PATCH /api/me` — update display name and anonymous flag
- `GET /api/players/search?q=...` — name search (403 if anonymous)
- `GET /api/players/{code}` — code lookup (403 if anonymous, 404 if target anonymous)
- `GET /api/friends` — list follows (empty if anonymous)
- `POST /api/friends/{code}` — follow (403 if anonymous)
- `DELETE /api/friends/{code}` — unfollow (always allowed)

**Frontend** (`static/account.html`, `static/account.js`, `static/style.css`):
- Profile section: display name editor, player code with copy, anonymous toggle
- Friends section: add by code, debounced search with follow buttons, friends
  list with remove buttons
- Friends section auto-disables when anonymous mode is toggled on

### Phase 2 — Complete

Daily recap of yesterday's games with friend comparisons, displayed on the home
page.

**Database** (`src/h21/db.py`):
- New method `get_recap(user_id, recap_date)` — returns the user's won games on
  a given date with all friends who played the same puzzles. Excludes anonymous
  users. API layer handles friend selection.

**API** (`src/h21/main.py`):
- `GET /api/recent-results` — returns the player's most recent 3 won games
  where at least one friend also played (not date-anchored)
- Helper `_compute_score(questions_asked, hints_used)` — internal scoring
  formula: `questions_asked + hints_used * 50`
- Helper `_select_friends_for_result(player_score, friends)` — selects up to 3
  friends per game: top performer + 2 closest if player is not top, or 3
  closest if player is top

**Frontend** (`static/home.html`, `static/home.js`, `static/style.css`):
- Recent results section above topic picker, fetched on page load
- Each game card shows topic/difficulty, ranked list of player + up to 3
  friends sorted by score, with empty slots shown as dashes
- Player's own row highlighted in gold
- Hidden when empty (no recent wins with friend overlap, anonymous user)
- Each card links to the full leaderboard page

### Phase 3 — Complete

Dedicated leaderboard page showing all non-anonymous winners of a specific
puzzle, ranked by performance score.

**Database** (`src/h21/db.py`):
- New method `get_puzzle_winners(puzzle_date, topic_slug, difficulty,
  requesting_user_id)` — returns all non-anonymous winners with `is_friend`
  annotation via LEFT JOIN on friends table

**API** (`src/h21/main.py`):
- `GET /api/leaderboard?topic_slug=...&difficulty=...&date=...` — returns
  ranked list of all non-anonymous winners with competition ranking, `is_self`
  and `is_friend` flags for client-side filtering

**Frontend** (`static/leaderboard.html`, `static/leaderboard.js`,
`static/style.css`):
- Table showing rank, player name, questions asked, hints used
- Player's own row highlighted in gold with "(you)" label
- "Friends only" toggle filters client-side without re-fetching
- Error handling for missing/invalid parameters

**Entry points**:
- Recent results cards (`static/home.js`) — "View full leaderboard" link
- Replay page (`static/replay.js`) — "View Leaderboard" button for completed
  games
- Account game history (`static/account.js`) — "Leaderboard" link for won games

### Phase 4 — Complete

Social engagement features: play-next discovery and leaderboard access from
game history.

**Database** (`src/h21/db.py`):
- New method `get_play_next(user_id, today)` — finds today's puzzles where
  friends have won but the user hasn't played, with friend counts

**API** (`src/h21/main.py`):
- `GET /api/play-next` — returns today's unplayed puzzles with friend activity

**Frontend** (`static/home.html`, `static/home.js`, `static/style.css`):
- "Friends Are Playing" section between recent results and topic picker
- Each entry shows topic/difficulty and "N friends played this"
- Clicking starts the game
- Hidden when empty

**Account page** (`static/account.js`):
- Game history now shows "Leaderboard" link alongside "Replay" for won games

## Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| Unidirectional follows, no confirmation | Simpler, matches "I choose who to compare against" |
| Anonymous as bidirectional social opt-out | Clean semantics — one toggle disables all social features in both directions |
| Preserve friend rows when anonymous | Toggling off restores everything, no re-adding needed |
| Recent results not date-anchored | Shows last 3 wins with friend overlap; avoids empty results when players skip days |
| Extend `/api/me` rather than new `/api/profile` | Avoids endpoint proliferation for own-account data |
| Player codes start at 4 chars | ~65k space, plenty for current scale, grow on exhaustion |
| Profile pictures deferred | High effort, not blocking for social comparisons |
| Play-next for today only | Discovery section shows only today's puzzles; keeps it fresh and actionable |
| Per-puzzle leaderboards, no global ranking | Avoids fragmentation and gaming; comparison is contextual |
