# Overview

## Goal

Create a script/workflow that generates a **local testing environment** for H21:
a runnable app instance pre-populated with realistic data so the developer can
log in and experience the app as a normal user would — having friends who play,
seeing play history (their own and their friends'), etc. Intended for debugging
and testing.

## Decisions (confirmed with user)

1. Seeded history is **fabricated**: canned topics, puzzles, games, and Q&A
   written directly to the database. No LLM calls during seeding.
2. The sandbox **supports live play with the real OpenAI API key** — no LLM
   stub; new games behave exactly like production.
3. The tool is a **reusable CLI command** alongside the existing invite/reset
   CLIs, with options (user count, history depth, seed, etc.).

## Outcome

Implemented as `h21-sandbox` (`src/h21/sandbox.py`, entry point in
`pyproject.toml`). Usage documented in `docs/development.md` ("Local Testing
Sandbox" section).

Key design points:

- **Isolation** via XDG overrides: the sandbox directory (default `./.sandbox`,
  gitignored) holds its own `XDG_CONFIG_HOME`/`XDG_DATA_HOME`, so the real
  database is never touched. `--serve` execs `h21` with those env vars set.
- **Config**: the real `~/.config/h21/config.toml` is copied in (or
  `OPENAI_API_KEY` from the environment), with `secure_cookies` and
  `auto_generate_missing_avatars` forced off (the latter would burn image-API
  credits on the fake accounts).
- **Seeded state**: a `dev` account (role `dev`), mutual-friend personas
  (`alice`, `bob`, ... via `--friends`), an anonymous friend (`zoe`), a
  tier-1 suggestion candidate (`felix`, follows dev only) and a tier-2 one
  (`gwen`, friend of a friend); 4 topics × 2 difficulties × `--days` of
  fabricated puzzles with hints; completed games with full Q&A transcripts,
  hint reveals, and backdated timestamps. One password for all accounts.
  Every account gets a real AI-generated profile picture: samples produced
  once by the in-game generator (`avatar.generate_avatar` with each persona's
  fixed adjective+noun subject from the game's own word lists) are committed
  to `assets/sandbox-avatars/` (512px webp, ~600KB total) and installed at
  seed time via `avatar.process_upload` — so seeding makes no image-API
  calls. `h21-sandbox --generate-samples` regenerates them (12 API calls);
  personas missing a sample fall back to a locally rendered Pillow identicon.
- **Realism guarantees**: a daily "popular" puzzle most personas play creates
  shared wins (recent-results feature); friends have completed games *today*
  (home-page friend avatars); dev has history on past days but nothing today,
  leaving today fresh for live play. Answers use the real LLM vocabulary
  (`yes/no/partially/depends/win`); per-topic question pools are written to be
  consistent with every solution in that topic's pool.
- **Timestamps**: rows are created through the normal `GameDatabase` API (which
  stamps "now"), then backdated in a fixup pass over a plain sqlite3
  connection.
- Deterministic under `--seed` (default 21).

Verified by 11 tests in `tests/test_sandbox.py` plus an end-to-end smoke test
(server started against a sandbox; login, friends, recent-results, history,
topics ranking, and friend-suggestions endpoints all returned the expected
seeded content).

## Status

Closed — implemented, tested, and documented on branch `sandbox-cli`.
