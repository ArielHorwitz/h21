# Topic flow

## Scope

Everything about a topic's life: a player suggesting it, its puzzle pools being built, it being accepted or turned down, its pools refilling, and it eventually running dry. These items were spread across the puzzle pool case (c254) and the UI overhaul case (7563) and are consolidated here as one problem, since they interact (thresholds, quotas, what the player is told and when).

How it works today is described in the puzzle pool case and in `docs/architecture.md`: a new topic builds both difficulty pools in the background (one batch of 100 plus validation each), is turned down if either keeps fewer than 50, and refills in the background below 50; a refill keeping fewer than 10 stops further refills (an interim guard), and an empty pool makes the topic answer "run out of puzzles". Suggesting happens on the `/suggest` page.

## Blind review (2026-10-12)

Two blind reviewers (Opus 5.5, GPT-6.1 Sol) analyzed the topic flow from a neutral brief (`topic-flow-review-brief.md`) and the code, without this casebook. Reports: `topic-flow-review-opus.md`, `topic-flow-review-sol.md`. The merged recommendations, with agreements, single-reviewer findings, disagreements and a proposed phase order, are in `topic-flow-recommendations.md`, awaiting the user's review. Notable new findings beyond the items below: validator replies are trusted without checking coverage or that kept names were generated (a malformed reply can permanently end a pool or reject a good topic), the daily draw isn't atomic, an empty pool can't trigger its own refill, seeded topics can fail invisibly, and the name-tidying prompt teaches the model to drop qualifiers.

## Status (2026-10-13)

Implemented on the `playtest` branch, per `topic-flow-decisions.md`, and running on the lab:

- Glossary terms adopted in schema, code, copy and docs (`docs/glossary.md`).
- Name tidying keeps what the topic covers.
- Series lifecycle (`series` table): available, winding down, finished, unavailable. Retry-once around every generation; the 50-solution gate per difficulty; a topic is ready if any series is available, with turned-down topics showing their counts; one refill at a time; atomic draw; empty-pool recovery; needs-attention flag.
- Topic previews: five model-chosen solutions from the normal pool, set aside and shown behind the topic name on Today and on Suggest.
- Exact-name duplicates refused (including mid-build); turned-down topics listed on Suggest and retryable; topic ideas on Suggest; no built-in topics.
- Control panel Topics tab: series status, pool size, last refill, refill and reopen.
- Tests with a fake model client cover build outcomes, retries, wind-down to finished, recovery and unavailable series.

Observed on a real build ("Pixar Movies"): expert kept 39, then 94 on its retry, so batches vary a lot and the retry earns its keep. The build took about five minutes, mostly high-effort validation (about 1m40s per 100 expert solutions).

## Open items

- Sandbox support for producing every topic and series state on demand, for the playtest.
- Build time at high effort (about five minutes with a retry): acceptable, or use a lower effort for generation and validation only.
- Deferred: a third reviewer per batch; dates (per-player local days); second seasons.
