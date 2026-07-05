# Social Engagement — Action Items

Concrete work items from the discussion on boosting engagement through smarter
recaps, game discovery, and leaderboard access.

---

## 1. Rename "recap" to "recent results"

The "daily recap" framing implies a fixed yesterday anchor. Now that the section
shows the last 3 games with friend overlap (not tied to a specific day), "recent
results" better describes what it is.

**Scope of rename:**

- API: `/api/recap` → `/api/recent-results`
- DB method: `get_recap()` → rename accordingly
- Frontend: `recap-section`, `recap-heading`, `recap-card`, `recap-ranking`,
  `recap-rank-*`, `recap-compare-link` CSS classes and element IDs
- Home page heading text: "Yesterday's Recap" → "Recent Results"
- `home.js`: `renderRecap()`, `recapSection`, `recapData` variables
- `home.html`: `recap-section` div ID

## 2. Rename "compare" to "leaderboard"

The compare page is already labeled "Leaderboard" in its subtitle. Align the
URL, filenames, and internals.

**Scope of rename:**

- Route: `/compare` → `/leaderboard` (serve `leaderboard.html`)
- API: `/api/compare` → `/api/leaderboard`
- Files: `compare.html` → `leaderboard.html`, `compare.js` → `leaderboard.js`
- All internal references: CSS classes (`compare-table`, `compare-self`, etc.),
  JS variables (`compareBody`, `compareContent`, etc.)
- Links in `home.js` (recap cards link to `/compare?...`)
- Links in `replay.js` ("View Leaderboard" button href)

## 3. Change recap logic: last 3 games with friend overlap

Replace the "yesterday's games" query with: the player's most recent 3 won
games where at least one non-anonymous friend also played the same puzzle.

**Changes:**

- DB: rewrite `get_recap()` query — drop the date filter, instead find the
  player's N most recent wins (by game completion time or puzzle date) that have
  at least one friend in the same puzzle's winners. Limit to 3.
- API: `/api/recent-results` returns the same response shape, just sourced from
  the new query. The friend selection logic (`_select_friends_for_recap`) stays
  the same.
- Frontend: no structural changes beyond the rename. Cards already show topic,
  difficulty, date, and friend comparisons.

## 4. Add "play next" section to home page

A new section below recent results: today's puzzles that friends have played but
the current player hasn't. Encourages competitive engagement.

**Design:**

- Heading: "Play Next" or "Friends Are Playing"
- Each entry shows: topic name, difficulty, and "N friends played this"
- Clicking an entry starts that game (links to the game page with the
  appropriate topic/difficulty)
- Only shows today's puzzles (unlike recent results which spans multiple days)
- Only shows puzzles the player has NOT yet played
- Hidden when empty (no friends have played today, or player has played
  everything)

**Changes:**

- DB: new method to find today's puzzles where friends have won but the
  requesting user hasn't played. Return topic name, slug, difficulty, and
  friend count.
- API: new endpoint, e.g. `GET /api/play-next` — returns the list. Respects
  anonymous mode (returns empty if anonymous).
- Frontend (`home.js`, `home.html`): new section rendered below recent results.
  Each item links to start the game.

## 5. Add leaderboard links to game history on account page

The account page's game history table currently has a "Replay" link for each
game. Add a "Leaderboard" link alongside it for won games.

**Changes:**

- API: `/api/history` response needs to include `topic_slug` and `date` per
  game (check if already present; `topic_slug` may need to be added).
- Frontend (`account.js`): for won games, add a leaderboard link next to the
  replay link, pointing to `/leaderboard?topic=...&difficulty=...&date=...`.

---

## Summary

| # | Item | Type |
|---|------|------|
| 1 | Rename recap → recent results | Rename |
| 2 | Rename compare → leaderboard | Rename |
| 3 | Last 3 games with friend overlap | Behavior change |
| 4 | "Play next" section on home page | New feature |
| 5 | Leaderboard links in game history | Enhancement |

Items 1 and 2 are mechanical renames. Item 3 is a query rewrite. Item 4 is the
main new feature (new endpoint + new UI section). Item 5 is a small addition to
existing UI.
