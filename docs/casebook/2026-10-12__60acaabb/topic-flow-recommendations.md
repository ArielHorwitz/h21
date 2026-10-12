# Topic flow: synthesized recommendations

Two blind reviewers (Opus 5.5 and GPT-6.1 Sol) worked independently from the same neutral brief (`topic-flow-review-brief.md`) and the code, with no access to this casebook. Their full reports are `topic-flow-review-opus.md` and `topic-flow-review-sol.md`. This document merges them: what both found, what only one found, where they disagree, and a proposed order of work. Nothing has been changed yet.

## The short version

1. **Make the generator trustworthy before trusting its numbers.** Today, one oddly formatted validator reply records a refill of zero, which permanently stops that pool and can turn down a good topic as "too narrow". The validator can also insert names that were never generated, and nothing in code prevents a past answer from being served again. Both reviewers rank this first among the fixes.
2. **Separate the two difficulties.** Publish a topic as soon as one difficulty is good. Movie Classics' 96 normal subjects should have shipped without expert.
3. **Make running out a normal ending, not an error.** Show per-difficulty availability, a "winding down" notice before the pool empties, and a "finished" state. Never send a player to a 503 behind a Play button.
4. **Fix scope where it's set.** The name-tidying prompt literally teaches the model to drop qualifiers (`"marvel movies and comics" -> "Marvel"`). Fix that now, then confirm the interpreted scope before building, and store that scope so generation, validation, hints and the host all agree on what the topic means.
5. **Be fair about failed suggestions.** Refund the daily suggestion when a build fails, with a separate cap on paid attempts.
6. **Remember rejected subjects, per difficulty**, so refills stop re-proposing them.

**A timing point both reports raise:** several of these need new columns or tables, and the app has no migration step. Before the relaunch, schema changes are free (the data is wiped anyway). After it, they need a migration or a reset. So schema-touching topic work fits best before the relaunch.

## Where both reviewers agree

| Issue | What both recommend |
|---|---|
| **Validator output is trusted blindly.** Unparseable replies give zero results instead of an error; KEEP lines aren't checked against the batch; exclusion of past answers relies only on the prompt. | Require one verdict per generated subject, accept only names from the batch (insert the generator's spelling), treat malformed or incomplete replies as technical failures, and deduplicate against all known subjects in code at insert time. |
| **A single low-yield refill ends a pool forever.** | Only two consecutive valid low-yield refills mark a pool as winding down; keep an operator action to reopen it. |
| **Both difficulties must pass 50, so a strong normal pool is thrown away.** | Make readiness per difficulty and publish what's good. |
| **Running out is a silent cliff.** Both buttons stay, every tap hits a 503. | Per-difficulty states (available, winding down, finished), a "nearly finished" notice, a finished state that keeps today's puzzle and history reachable, and finished topics moved out of the main list. Don't recycle old subjects (friends remember answers). |
| **Scope drift.** | Fix the normalizer's qualifier-dropping example immediately; add a preview/confirm step before building; store a scope line and feed it to every prompt. |
| **Rejected subjects are forgotten.** | Store them with reason and difficulty; exclude them from future generation for that difficulty only (a subject too obscure for normal may suit expert). |
| **Failed builds cost a suggestion; transient errors become permanent failures.** | Retry transient errors with backoff; refund the suggestion on failure; keep a separate daily attempt cap so refunds can't become unbounded spending. |
| **No observability.** | Record rejection reasons, parse failures, insert counts and token usage; give the operator a pool-health view (remaining, winding down, runway). |
| **The `h21-pool` experiment tool doesn't match production** (batches of 25 vs 100, rejects excluded vs not, two-strike vs one-strike stop). | Align it with production before using it to set thresholds. The "100 to 150 subjects" estimate is a hypothesis, not a forecast. |
| **Leave alone:** build latency, model cost, recycling, a queue service. | Agreed. |

## Found by only one reviewer

**Opus only:**
- **Seeded topics can fail invisibly.** Notable People and World Geography have no owner, so if their first build fails (an API hiccup at first boot), nobody sees it, nobody can dismiss it, and it's never retried. Recommends that seeded topics skip the threshold and get rebuilt on startup if failed.
- **Contradictory copy:** "Try something broader" encourages exactly the broad names that cause scope drift, and blames the whole topic when only expert fell short.
- **Re-suggesting someone else's failed topic deletes their card** and reassigns it; a topic that is still being built returns "already exists" to others, who can't find it. Return a link to the existing topic instead.
- A "New, suggested by X" tag on Today for a topic's first days (optional social glue).

**Sol only:**
- **The draw isn't atomic.** The subject is removed from the pool before the daily puzzle is saved, and hint generation happens in between. A crash then loses the subject from both. Sol confirmed this with a local check. Fix: draw and save in one short transaction, then generate hints separately.
- **An empty pool can't trigger its own recovery.** Once a difficulty is empty and has any refill on record, the request returns 503 before reaching the refill trigger (also confirmed locally). Background refill failures aren't retried, and startup doesn't check low pools.
- **Concurrency gaps:** if one difficulty's build task fails, its sibling keeps running after the topic is marked failed; two refills can insert the same subject; the quota check and increment can race.
- **Status polling stops after a single failed fetch**, so a finished build can look stuck on a phone; Dismiss ignores errors.
- **Dates:** the server uses its local date and the browser its own, and a request crossing midnight can split dates.
- **Slug collisions:** non-ASCII and punctuation are stripped from slugs, so different names can collide.
- **Validator criteria** should explicitly require the subject to exist, be uniquely identifiable and be answerable with yes/no facts.
- An optional "What should count?" field, freezing scope once published, and a "Report this puzzle" action.

## Where they disagree

| Question | Opus | Sol | My take |
|---|---|---|---|
| **How to rescue near-miss topics** | One top-up batch for the short difficulty before judging; launch normal-only if expert stays under ~20; later lower the normal floor to ~30 once endings are graceful. | First just decouple the difficulties at the existing 50; then pilot a 30 floor with manual quality checks; at most one small top-up within a budget. | Decouple first (both agree it's the root fix); one top-up for a marginal difficulty is cheap and probably rescues cases like Movie Classics expert. Decide the 30 floor after measuring. |
| **What the preview shows** | Normalized name, one-line scope, **five sample subjects**, narrower alternatives as tappable chips. | Interpreted name and scope with Edit/Create; **no sample subjects**, because real generated subjects could become future puzzles and spoil them; optional "what should count?" field. | Sol's spoiler point is right if samples come from the real pool. Samples generated separately from the build would avoid it, but cost a call and can mislead. I'd start with name, scope line and alternatives, no samples. |
| **How much reliability engineering** | Small, targeted fixes. | Broader: build IDs, task cancellation, SQLite leases (later), a periodic recovery task, a build semaphore. | For this audience, the targeted fixes plus atomic draw and empty-pool recovery are enough; skip leases and build IDs. |
| **Refunds** | Refund any failure, cap attempts at ~10/day. | Reserve a slot, refund exactly once if nothing publishes, cap attempts ~6/day, idempotent build IDs. | Same idea; the simpler version is fine. |

## Proposed order

**Phase 1: correctness (small, mostly invisible).**
Validator coverage and batch matching; code-side dedupe at insert; atomic draw; empty-pool recovery and retries for transient errors; two-strike exhaustion with an operator reset; seeded topics retried on startup. These stop false endings and repeats, and make the numbers trustworthy before anything is tuned.

**Phase 2: the player-facing flow.**
Normalizer fix (trivial, could go first); per-difficulty readiness and lifecycle states (available, winding down, finished) on Today and Suggest; a near-miss top-up; refund on failure with an attempt cap; better failure copy; polling that survives a failed fetch; scope preview and stored scope line used by every prompt.

**Phase 3: memory and measurement.**
Rejection records per difficulty; observability (reasons, counts, tokens, pool health); align `h21-pool` with production; then run the measurements both reviewers list (gate noise on repeated builds, why rejection climbs, expert calibration) before deciding thresholds like a 30 floor.

**Deferred or skipped:** recycling subjects; a queue service or multi-process leases; "Report this puzzle"; the "New, suggested by X" tag (cheap, could come later).

## Decisions for the user

1. Is the phase order right, and should the schema-touching parts (stored scope, rejection records, per-difficulty status) land before the relaunch?
2. Preview contents: name, scope and alternatives only (no sample subjects), or include samples?
3. Near-miss rescue: decouple plus one top-up now, decide a lower floor after measuring?
4. Anything to drop: e.g. the optional "What should count?" field, or the finished-topics section?
