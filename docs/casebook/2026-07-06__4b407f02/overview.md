# UI Overhaul — Overview

## Status: implemented

Four changes to improve the home page flow and fix general UI issues.

## 1. Navbar pill with translucent background

Added `background`, `backdrop-filter`, `padding`, and `border-radius` to
`.nav-bar` in `style.css` to wrap the three nav icons in a floating translucent
pill.

## 2. Table horizontal scroll containment

Added `.table-scroll-wrapper` CSS class (`overflow-x: auto; max-width: 100%`).
Wrapped the following tables in scroll wrappers:
- Game history table (`account.js`)
- Invites table (`control.js`)
- Invite requests table (`control.js`)
- Activity log table (`control.js`)
- Users table (`control.js`)

The query result section already had `overflow-x: auto`.

## 3. Remove "Play Next" section, merge friend signals into puzzle list

Removed the "Friends Are Playing" / "Play Next" section entirely:
- Removed `/api/play-next` endpoint from `main.py`
- Removed `get_play_next()` from `db.py`
- Removed `renderPlayNext()`, `loadPlayNext()`, and related code from `home.js`
- Removed `#play-next-section` div from `home.html`
- Removed `.play-next-*` CSS styles

Added `get_topics_ranked()` to `db.py` which:
- Queries all topics with total play count
- Finds friend activity on today's puzzles (avatar info per difficulty)
- Sorts by `play_count + friend_count * 50` descending, alphabetical tiebreak

Updated `/api/topics` endpoint to use `get_topics_ranked()`.

**Home page section order (after):**
1. Recent Results
2. Friend Suggestions
3. Today's Puzzles (sorted by popularity + friend boost, with inline avatars)
4. Request a Topic
5. Replay

## 4. Topic card expansion for friend avatars (option C)

Changed `.topic-card` from single-row flex to column layout with a
`.topic-card-header` row. When friends have played a puzzle, extra
`.topic-friends-row` elements appear below the header, one per difficulty,
showing a label and friend avatars.

```
+----------------------------------+
| Jazz Music    [Normal] [Expert]  |
|   Normal: [avatar] [avatar]      |
|   Expert: [avatar]               |
+----------------------------------+

+----------------------------------+
| Ancient Rome  [Normal] [Expert]  |
+----------------------------------+
```

## Files changed

| File | Change |
|------|--------|
| `static/style.css` | Navbar pill, table scroll wrapper, topic card friend rows, removed play-next styles |
| `static/home.html` | Removed play-next-section div |
| `static/home.js` | Removed play-next code, updated renderTopics for friend avatars |
| `static/account.js` | Wrapped history table in scroll wrapper |
| `static/control.js` | Wrapped invites/requests/activity/users tables in scroll wrappers |
| `src/h21/db.py` | Added `get_topics_ranked()`, removed `get_play_next()` |
| `src/h21/main.py` | Updated `/api/topics` handler, removed `/api/play-next` endpoint |
