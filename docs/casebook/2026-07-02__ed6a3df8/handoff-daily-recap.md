# Handoff: Daily Recap

Phase 2 of the social comparison feature. Adds a recap of yesterday's games
with friend comparisons, displayed on the home page.

## Design Constraints

- **No new tables or columns.** The recap is derived on demand from existing
  data: `games`, `hint_reveals`, `friends`, `accounts`.
- **"Yesterday"** is `date.today() - timedelta(days=1)` — server local time,
  same logic as daily puzzle rotation.
- **Only won games** appear in the recap. Losses and in-progress games are
  excluded.
- **Anonymous players** are excluded from all recap data — both as the
  requesting player (return empty recap) and as friends (anonymous friends
  don't appear in comparisons).

## Scoring

Games are ranked by the formula:

```
score = questions_asked + hints_used * 50
```

Lower is better. This formula is internal — never shown to the user. The UI
shows `"N questions + M hints"` (or `"N questions"` when no hints were used).

## Friend Selection (per game)

Each game in the recap shows exactly 3 friend slots:

- If the player is **not** the top performer among friends: show the **top
  performer** + the **2 friends closest** to the player's score.
- If the player **is** the top performer: show the **3 friends closest** below
  the player's score.
- If fewer than 3 friends played, show however many there are with empty slots.
- If 0 friends played, still show the game with all 3 slots empty.

"Closest" means smallest absolute difference in score. Ties can be broken
arbitrarily (e.g. by `user_id`).

## Database Layer (`src/h21/db.py`)

### New method

```python
def get_recap(self, user_id: int, recap_date: date) -> list[dict]:
    """Get recap data for a user on a given date.

    Returns a list of the user's won games on recap_date, each with:
    - topic_slug, topic_name, difficulty, date
    - questions_asked, hints_used (for the requesting user)
    - friends: list of friends who also won the same puzzle (same
      topic_slug + difficulty + date), each with:
      - display_name (falls back to username), player_code
      - questions_asked, hints_used

    Excludes anonymous friends. Returns empty list if the user is
    anonymous.

    Does NOT perform friend selection/filtering — returns ALL friends
    who played each game. The API layer handles the top+closest logic.
    """
```

The query shape:

1. Check if the user is anonymous → return `[]` if so.
2. Get all of the user's won games on `recap_date`:
   ```sql
   SELECT g.game_id, g.topic_slug, t.name AS topic_name, g.difficulty,
          g.date, g.questions_asked
   FROM games g
   JOIN topics t ON g.topic_slug = t.slug
   WHERE g.user_id = ? AND g.date = ? AND g.result = 'win'
   ```
3. For each game, count hints:
   ```sql
   SELECT COUNT(*) FROM hint_reveals WHERE game_id = ?
   ```
4. Get friends' won games on the same puzzles. This can be a single query
   joining `friends` → `accounts` → `games` → `hint_reveals`:
   ```sql
   SELECT a.display_name, a.username, a.player_code,
          g.questions_asked,
          (SELECT COUNT(*) FROM hint_reveals h WHERE h.game_id = g.game_id) AS hints_used
   FROM friends f
   JOIN accounts a ON f.friend_id = a.user_id
   JOIN games g ON g.user_id = a.user_id
                AND g.date = ?
                AND g.topic_slug = ?
                AND g.difficulty = ?
                AND g.result = 'win'
   WHERE f.user_id = ? AND a.anonymous = 0
   ```

Performance note: this is a small number of queries for a small dataset. No
optimization needed. If it ever becomes a concern, the friends' games query
could be batched across all of the user's games, but that's premature.

## API Layer (`src/h21/main.py`)

### New endpoint

#### `GET /api/recap`

Returns yesterday's recap for the authenticated user.

```
Response:
[
  {
    "topic_name": "Animals",
    "difficulty": "hard",
    "date": "2026-07-01",
    "my_result": {
      "questions_asked": 12,
      "hints_used": 1
    },
    "friends": [
      {
        "display_name": "Alice",
        "player_code": "A1B2",
        "questions_asked": 8,
        "hints_used": 0
      },
      ...
    ]
  },
  ...
]
```

The endpoint is responsible for:

1. Calling `database.get_recap(user_id, yesterday)`.
2. For each game, applying the friend selection logic:
   - Compute scores for the player and each friend.
   - Determine if the player is the top performer.
   - Select 3 friends per the rules above.
3. Returning the filtered results.

Returns an empty list if the user is anonymous, played no games yesterday, or
no games were won.

Auth: standard user auth.

## Frontend Changes (`static/home.html`, `static/home.js`)

### Recap widget on the home page

Add a recap section above the existing topic picker. Fetched on page load via
`GET /api/recap`.

#### Non-empty state

For each game in the recap:

```
┌────────────────────────────────────────┐
│ Animals (Hard)                         │
│                                        │
│ You: 12 questions + 1 hint             │
│                                        │
│ 1. Alice    —  8 questions             │
│ 2. You      — 12 questions + 1 hint    │
│ 3. Bob      — 14 questions + 2 hints   │
│    ───                                 │
│    ───                                 │
└────────────────────────────────────────┘
```

The ranking list shows the player and up to 3 friends in sorted order by score
(best to worst). The player's own row is highlighted/bolded. Empty friend slots
are shown as dashes or blank rows.

Hint count display: `"N questions"` when 0 hints, `"N questions + M hint"` when
1 hint, `"N questions + M hints"` when 2+ hints.

#### Empty state

When the recap list is empty (no won games yesterday, or user is anonymous):

```
No recap available — no won games from yesterday.
```

### Style notes

Follow existing vanilla JS patterns. Reuse existing CSS classes where possible.
The recap should be visually distinct from the topic picker but use the same
general styling (card-like sections, consistent spacing).

## Testing Considerations

- User with 0 won games yesterday → empty recap.
- User with won games but 0 friends → games shown, all friend slots empty.
- User with won games and friends who played same puzzles → correct selection.
- Friend selection when player is top performer → 3 closest below.
- Friend selection when player is not top → top performer + 2 closest.
- Fewer than 3 friends played → show available friends, rest empty.
- More than 3 friends played → correct top+closest filtering.
- Anonymous user → empty recap.
- Anonymous friend excluded from friend list in recap.
- Score formula correctness: hints_used * 50 + questions_asked.
- Ranking display order: best score first.

## What This Does NOT Include

- Comparison page for a single game (Phase 3).
- Live "today" comparison.
- Any persistence/caching of recap data.
