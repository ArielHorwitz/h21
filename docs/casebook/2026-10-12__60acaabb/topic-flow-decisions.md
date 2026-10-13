# Topic flow: decisions from reviewing the recommendations

The user's responses to `topic-flow-recommendations.md` (2026-10-13), organized. Nothing is implemented yet. "Open" marks what still needs discussion.

## Principles

- **Keep the model simple.** A topic is just its name; that name is what generation and validation see. No extra scope field, no topic validation gates beyond "can puzzles be made".
- **Trust the models, guard with a retry.** No heavy validation machinery. Any bad outcome gets one retry; a failure is believed only if the retry fails too.
- **The admin is the safety valve.** Rare failures (refunds, stuck pools) are handled from the control panel rather than with automatic machinery.
- **Small audience.** Races and scale problems should be handled correctly but simply.

## Decisions

### Generation and validation
- **Retry once on any bad outcome:** a malformed reply, too few subjects kept, or a transient error. Only if the retry also fails is the result treated as real (low yield, or an error).
- This replaces the reviewers' heavier proposals (coverage checks, batch matching, code-side dedup).
- **Optional, to consider:** a third model that sanity-checks the final kept list, in case the generator and validator go off the rails in the same way.
- **Rejected puzzle answers:** left as is. They aren't remembered or excluded; a later refill accepting what an earlier one rejected is a welcome second opinion, and an all-rejected batch already signals the topic is running dry.
- **Which model:** generation, validation, name tidying and hints all use the game model (`gpt-6-luna`, high effort). A separate generation model would be a config option if ever wanted.

### Building a topic
- **One build task covering both difficulties.** If either difficulty *errors* (after its retry), the whole build fails loudly. Low yield is not an error (see thresholds).
- **Thresholds:** judge each difficulty separately. A topic publishes if it has any subjects at all; a difficulty with a small pool starts out "winding down". A topic with no subjects at all isn't published. The fixed 50-subject gate goes away.
- **Seeded topics:** none. A fresh instance starts empty, and the admin creates the first topics from the Suggest page.
- **Example topics on the Suggest page:** about 20 tappable examples of good topics (e.g. pop songs, Roman history), so the admin can stand up a new instance quickly and players get ideas.
- **Name tidying:** keep the cleanup (capitalization, spelling, display), but it must never change what the name means. Remove the example that teaches dropping qualifiers.
- **Same topic suggested twice at once:** never reassign or delete someone else's topic; return a link to the existing one. Handle the race correctly but simply.
- **Rejected topics:** recorded and listed on the Suggest page so players can rephrase (e.g. "Marvel Comics" turned down, try "Marvel Comics and Movies"). Not enforced.

### Topic preview (sample subjects)
- When a topic is built, a model picks **five representative subjects** from the first batch, showing the range of possible answers. They're moved to the used set (as if played), so they're never drawn as a daily puzzle and stay excluded from later batches. No spoilers.
- Take at most about 10% of the pool, so only for topics with enough subjects (roughly 50 or more).
- **Shown to everyone,** not just the creator: a player tapping "Disney" sees that theme parks are in scope. This replaces the "confirm before building" preview, and solves the Disney problem after the fact: the creator sees the samples and can suggest a narrower topic.
- *Open:* where exactly players see it (topic card, a topic info sheet, the game intro).

### Lifecycle and endings
- **Per-difficulty states:** available, winding down (a separate threshold), finished. Shown on Today as tags or labels; finished topics sorted last. A "New" tag for recently created topics fits the same mechanism.
- **Refills:** one retry before believing a low-yield refill, then the difficulty winds down. A lock prevents several refills running at once.
- **Empty or stuck pools:** retries with backoff up to a maximum; past that, flag the topic in the control panel (with an admin notice) where the admin can trigger a refill manually.
- **Atomic draw:** pick and save the day's puzzle in one transaction, generate hints afterwards.
- **Observability:** the pool status the admin needs lives in the control panel.

### Quota
- **A suggestion uses quota the moment it's submitted,** whatever happens next. No automatic refunds; the admin can reset or adjust quotas from the control panel. Counting failed and successful suggestions separately was floated but isn't needed.

### Skipped
- Validator criteria for topics, an optional "what should count" field, "Report this puzzle", recycling old subjects, a queue service, leases and build IDs.
- Freezing scope once published is moot, since a topic is just its name and that never changes.
- Aligning `h21-pool` with production: optional.

## Open

1. **Near-miss topics** need a deeper discussion (with the gate gone, mostly a question of the winding-down threshold and what a small starting pool looks like).
2. **Where the preview is shown** to players.
3. **The optional third-model check:** whether it's worth it.
4. **Dates** (filed as a separate issue): the intended model is Wordle-like, where each player's day follows their own local time. Today the server uses its own local date for everyone. Requests crossing midnight and games spanning midnight need a rule. Not game-breaking now.
5. **How the user will test all of this:** the topic flow has many states (building, retrying, winding down, finished, failed, rejected), so the sandbox needs a way to produce each one on demand.
