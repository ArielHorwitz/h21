# Topic flow: decisions from reviewing the recommendations

The user's responses to `topic-flow-recommendations.md` (2026-10-13), organized. Nothing is implemented yet. "Open" marks what still needs discussion.

## Terminology

Settled before the work starts and recorded in `docs/glossary.md`: **topic** (the name), **series** (topic + difficulty, which owns pools, thresholds and lifecycle states), **puzzle** (a series' daily instance), **game** (one player's attempt at a puzzle, with its own share code), **answer** (a puzzle's secret; what pools hold and previews sample), **pool**. Where this document says "puzzle" for a topic + difficulty, read **series**. Since the relaunch wipes the data, the schema and code are renamed to these terms as part of the work (e.g. `daily_puzzles` becomes `puzzles`, `solution` becomes `answer`), with no migration.

## Principles

- **Keep the model simple.** A topic is just its name; that name is what generation and validation see. No extra scope field, no topic validation gates beyond "can puzzles be made".
- **Trust the models, guard with a retry.** No heavy validation machinery. Any bad outcome gets one retry; a failure is believed only if the retry fails too.
- **The admin is the safety valve.** Rare failures (refunds, stuck pools) are handled from the control panel rather than with automatic machinery.
- **Small audience.** Races and scale problems should be handled correctly but simply.

## Decisions

### Generation and validation
- **Retry once on any bad outcome:** a malformed reply, too few subjects kept, or a transient error. Only if the retry also fails is the result treated as real (low yield, or an error).
- This replaces the reviewers' heavier proposals (coverage checks, batch matching, code-side dedup).
- **Deferred:** an optional third reviewer per batch (generator, validator, reviewer), in case the first two go off the rails in the same way.
- **Rejected puzzle answers:** left as is. They aren't remembered or excluded; a later refill accepting what an earlier one rejected is a welcome second opinion, and an all-rejected batch already signals the topic is running dry.
- **Which model:** generation, validation, name tidying and hints all use the game model (`gpt-6-luna`, high effort). That stays; no separate generation model.

### Building a topic
- **One build task covering both difficulties.** If either difficulty *errors* (after its retry), the whole build fails loudly. Low yield is not an error (see thresholds).
- **Puzzles, not topics, have states.** A "puzzle" here is a topic and difficulty pair; each has its own threshold and lifecycle.
- **Thresholds: keep the 50-subject gate, per difficulty.** A difficulty with fewer than 50 subjects isn't offered; the topic publishes if at least one difficulty passes. The gate stays partly because of the preview: taking 5 samples from the narrowest possible pool (50) uses 10% of it, which is acceptable, while smaller pools would lose too much.
- **Near misses: no special handling.** A topic at 45 vs 51 is close to a coin toss, and that's fine. The turned-down message gives the numbers ("We could only make 45 normal and 30 expert subjects; at least 50 are needed"), and the player can simply try again.
- **Seeded topics:** none. A fresh instance starts empty, and the admin creates the first topics from the Suggest page.
- **Example topics on the Suggest page:** about 20 tappable examples of good topics (e.g. pop songs, Roman history), so the admin can stand up a new instance quickly and players get ideas.
- **Name tidying:** keep the cleanup (capitalization, spelling, display), but it must never change what the name means. Remove the example that teaches dropping qualifiers.
- **Duplicate topics: exact name only.** Topics are identified by their tidied name. If that name already exists or is being built, the suggestion is refused with "already exists" (no link, since a topic still being built has nothing to link to). No attempt to detect near-duplicates like "Roman History" vs "Ancient Roman History": that would need a model and is subjective. Never reassign or delete someone else's topic.
- **Turned-down topics:** recorded and listed on the Suggest page with their numbers. No guidance on how to rephrase and no enforcement; suggesting the same name again is allowed (it may pass the second time).

### Topic preview (sample subjects)
- When a topic is built, a model picks **five representative subjects** from the first batch: a deliberately diverse sample showing the range of possible answers (people, places, events, objects...), not five random ones, which could all look alike. They're moved to the used set (as if played), so they're never drawn as a daily puzzle and stay excluded from later batches. No spoilers.
- Always exactly five; the 50-subject gate guarantees the pool can afford it.
- **Shown to everyone,** not just the creator: a player tapping "Disney" sees that theme parks are in scope. This replaces the "confirm before building" preview, and solves the Disney problem after the fact: the creator sees the samples and can suggest a narrower topic.
- *Open:* where players see it. Today probably needs more room per topic anyway (per-difficulty tags), perhaps a collapsible info section.
- *Open (small):* whether the five come from the normal pool, the expert pool, or both.

### Lifecycle and endings
- **Per-difficulty states:** available, winding down (a separate threshold), finished. Shown on Today as tags or labels; finished topics sorted last. A "New" tag for recently created topics fits the same mechanism.
- **Refills:** one retry before believing a low-yield refill, then the difficulty winds down. A lock prevents several refills running at once.
- **Empty or stuck pools:** a single retry; past that, the control panel shows the pool's state and lets the admin trigger a refill. Observability lives there.
- **Atomic draw:** pick and save the day's puzzle in one transaction, generate hints afterwards.
- **Observability:** the pool status the admin needs lives in the control panel.

### Quota
- **A suggestion uses quota the moment it's submitted,** whatever happens next. No automatic refunds; the admin can reset or adjust quotas from the control panel. Counting failed and successful suggestions separately was floated but isn't needed.

### Later
- **Second seasons:** once a puzzle is finished, relaunch it as a "season 2" (and beyond), so latecomers can keep playing. A long way off.

### Skipped
- Validator criteria for topics, an optional "what should count" field, "Report this puzzle", recycling old subjects, a queue service, leases and build IDs.
- Freezing scope once published is moot, since a topic is just its name and that never changes.
- Aligning `h21-pool` with production: optional.

## Open

1. **Today's layout:** room for per-difficulty tags and the topic preview (maybe a collapsible info section).
2. **Preview source:** normal pool, expert pool, or both.
3. **Deferred:** the third reviewer per batch, and dates (Wordle-like per-player local days; today the server's local date applies to everyone; midnight-crossing requests and games need a rule; not game-breaking now).
4. **Testing:** once built, the sandbox needs a way to produce each topic and puzzle state on demand for the playtest.
