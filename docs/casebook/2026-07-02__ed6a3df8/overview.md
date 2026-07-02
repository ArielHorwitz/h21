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

## Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| Unidirectional follows, no confirmation | Simpler, matches "I choose who to compare against" |
| Anonymous as bidirectional social opt-out | Clean semantics — one toggle disables all social features in both directions |
| Preserve friend rows when anonymous | Toggling off restores everything, no re-adding needed |
| Yesterday not today | Everyone sees the same recap regardless of play order |
| Extend `/api/me` rather than new `/api/profile` | Avoids endpoint proliferation for own-account data |
| Player codes start at 4 chars | ~65k space, plenty for current scale, grow on exhaustion |
| Profile pictures deferred | High effort, not blocking for social comparisons |
| Recap on home page | Ship fast, iterate UI/UX later |
