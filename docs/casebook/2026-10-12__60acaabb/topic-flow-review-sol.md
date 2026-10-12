# H21 topic flow review

## Top recommendations

1. **Make topic scope a player-approved promise.** Preserve the creator's intended boundaries, show a short scope preview before building, and use that same scope in generation, validation, hints and hosting. Do not solve scarcity by silently broadening a topic.
2. **Accept useful difficulties independently and allow finite runs.** Movie Classics' 96 normal subjects are worth publishing even if expert has only 41. Two difficulties should be an aspiration, not a condition that wastes a good pool.
3. **Separate low supply from broken generation.** Validate model response coverage before using yield to make product decisions. Add bounded retries and recovery for empty pools. A malformed response or temporary outage must not permanently end a topic.
4. **Tell players when a difficulty is winding down or finished.** Retain today's puzzle and past results, replace misleading play buttons, and offer another topic. Never recycle answers or widen scope automatically.
5. **Make failed suggestions fair without allowing unlimited paid attempts.** Refund unsuccessful builds against the player-facing suggestion allowance, while retaining a separate, bounded attempt limit for the operator's costs.

Keep FastAPI, SQLite, vanilla JS and background generation. The supplied cents-per-build costs do not justify a new queue service, elaborate capacity prediction, or replacing the model before fixing the flow.

## Basis and limits

This review uses the supplied brief, local documentation and source only. The numerical experiment results and Disney example are supplied observations, not measurements reproduced here. Recommendations and effort estimates are judgments for one developer familiar with this application. No model calls, external research or production access were used.

The documentation is partly stale: several orientation documents say the topic allowance defaults to one, whereas [the configuration](src/h21/config.py:66) defaults to three, consistent with the brief. Account-specific limits can differ. Code takes precedence for behavior.

## Current flow, end to end

| Stage | Player experience | System behavior |
|---|---|---|
| Suggest | A single name field, examples, and remaining daily allowance. No scope explanation or review step. | Checks allowance and the raw name's 1 to 100 character length. Calls the model to normalize it to an English display name, then derives the slug. |
| Resolve identity | Existing topics produce a generic error. The creator sees the normalized name only after submitting. | An existing nonfailed slug returns 409. Anyone can retry a failed slug, deleting its old topic, pools and refill records first. Normalization failures and duplicate conflicts do not consume the suggestion allowance, but can incur a model call. |
| Build | A message says creation takes a minute or two. Suggest and Today poll every four seconds while a visible topic is generating. Only its creator sees a generating or failed topic. | Persists the topic and increments usage before starting an in-process background build. Generates and validates a requested batch of 100 for each difficulty concurrently: four build calls plus the preceding normalization call. Startup resumes topics still marked generating. |
| Decide | Ready topics appear for everyone with Normal and Expert links. A failed topic gets a reason and Dismiss. | Removes exact cross-difficulty pool duplicates from expert, then requires at least 50 remaining subjects in **each** pool. Otherwise both difficulties remain unplayable. Technical failures use a different message but the same failed state. |
| Draw | Players share the day's answer for their chosen topic and difficulty. The first player can wait for hint generation. | On the first request for that server date and difficulty, a process-local lock protects a random pool draw. The row is deleted, hints are requested, and the daily puzzle is saved. An ordinary hint failure permits an empty hint list, with later backfilling. No request means no draw that day. |
| Refill | Usually invisible. The pool does not need to refill for every player. | After a new daily puzzle is saved, a pool below 50 starts a background generation/validation pair unless that difficulty is already refilling or its latest recorded insertion count is below 10. Exclusions include accepted subjects in both pools and all past daily puzzles. |
| Wind down | No advance indication. Both play links remain visible because the topic remains ready. | One successful refill with fewer than 10 actual insertions permanently suppresses further refills at that difficulty. Remaining subjects can still be drawn. |
| Empty | Starting a new daily puzzle returns “This topic has run out of puzzles.” | Returns 503. It does not distinguish a finite topic from a recoverable empty pool. An already saved puzzle for today still works. The other difficulty can remain playable. |

Implementation: [submission](src/h21/main.py:1294), [build and refill](src/h21/main.py:314), [draw](src/h21/main.py:276), [topic listing](src/h21/db.py:214), [suggestion interface](static/suggest.js:103), [Today interface](static/home.js:207).

**Supply is consumed per topic, difficulty and active date, not per player.** A pool of 100 subjects provides 100 new puzzle dates if that difficulty is requested daily. It can last longer in calendar time when skipped. Conversely, the exclusion list can already contain about 200 pooled subjects immediately after a broad topic builds, before anyone has played. Experiments about “already used” subjects must be interpreted against this larger production exclusion set.

## Problems and risks

Severity describes the consequence when the problem occurs. Likelihood is uncertain where the brief gives no observations.

| Problem | Who it affects and how badly | Evidence and implication |
|---|---|---|
| The name is the entire topic contract | **High:** creators get a different topic and all players waste guesses based on an incorrect boundary. | Disney demonstrates ambiguity. The normalization prompt even maps “marvel movies and comics” to “Marvel”, explicitly discarding scope. Generator and validator can agree with each other while disagreeing with the player. |
| Acceptance couples two unequal pools | **High:** creators lose usable work and normal players lose good puzzles. **Low financial impact** per build for the operator. | The minimum is checked after exact overlap removal. Movie Classics at 96/41 fails, World Geography expert at 63 passes. A single batch's yield is neither a proof of total capacity nor proof of quality. |
| A finite supply is presented as indefinite daily service | **High:** regular players encounter an avoidable dead end. | No lifecycle information is returned in topic listings. Normal and expert can finish at different times while both retain active links. Broad topics look durable in the observations, but no topic is guaranteed infinite. |
| Exhaustion is inferred from one batch and conflated with response defects | **High:** good topics can be permanently suppressed. | A successful API response containing no parseable KEEP/REJECT lines produces zero results rather than an error. That becomes a recorded zero-insertion refill. The latest count alone determines exhaustion. Duplicate conflicts and short responses also reduce inserted count. |
| Empty pools cannot initiate normal recovery | **High consequence, unknown frequency:** an outage can leave a ready difficulty permanently unavailable without intervention. | Exceptions in background refill are logged, not scheduled for retry. Subsequent fresh daily draws can retrigger refilling while subjects remain, but an empty pool with any prior refill record returns 503 before reaching the refill trigger. Existing daily puzzles also return before that trigger. Startup resumes builds, not low ready pools. |
| Rejected candidates are forgotten | **Medium:** operator pays for repeat work and players may wait longer or lose valid supply. | Only accepted pooled and drawn subjects enter exclusions. Rejections and their reasons are not retained by the application. Difficulty mismatch is not a universal rejection: a valid normal subject can be rejected for expert, and vice versa. |
| Validation is not a trustworthy boundary | **High:** players receive repeats, invented or poorly suited answers. | The parser accepts any KEEP name without checking it belongs to the submitted batch or requiring one verdict per candidate. The prompt asks about ambiguity and fit, but does not explicitly require factual existence and reliable yes/no answerability. Generation and validation share the same configured client, so model errors may be correlated. |
| Duplicate prevention has gaps | **Medium:** familiar answers repeat and expert supply can be understated. | SQLite uniqueness applies only to exact strings within one difficulty's undrawn pool. Initial cross-difficulty cleanup removes exact expert overlaps but does not resolve aliases. Later simultaneous refills take exclusions before their model calls, with no equivalent cleanup afterward. Subjects in past puzzles are excluded by prompt, without an insertion-time constraint against them. |
| Failed builds spend the creator's allowance | **Medium:** experimentation feels punished, including when the system breaks. | Usage increments before the build. Retry rebuilds everything and consumes another suggestion. Dismiss does not refund. The same failed topic can be retried by someone else, erasing its previous creator's status and useful partial pool. |
| Concurrency and restart handling are incomplete | **High consequence, probably uncommon in a small audience:** lost supply, extra costs and inconsistent state. | Draw deletion commits before the daily puzzle is recorded. A crash during hints loses that subject from both pool and history. A restarted partial build refills both difficulties again. If one task in the build's gather fails, its sibling can continue after the topic is marked failed, racing a dismissal or replacement. Locks and in-flight sets protect only one process. |
| Cost and quota controls have holes | **Low current impact, medium if repeated:** operator pays for unwanted work and the allowance loses meaning. | Allowance is checked before awaiting normalization and incremented later, so simultaneous requests can pass the same remaining slot. Duplicate submissions still call normalization. There is no application-wide build concurrency limit or separate failed-attempt budget. |
| Progress can freeze on a phone | **Medium:** a finished build can look stuck and invite unnecessary resubmission. | Polling schedules its next attempt only after a successful topics fetch. One error stops the loop. The displayed one-to-two-minute message is already useful, but there is no recovery status. Dismiss ignores non-OK responses. |

Sources for prompt and integrity findings: [normalization](src/h21/llm.py:152), [generation and validation prompts](src/h21/llm.py:104), [validation parser](src/h21/llm.py:355), [pool storage and duplicate cleanup](src/h21/db.py:402), [quota updates](src/h21/db.py:1338), [startup](src/h21/main.py:185).

Two additional small issues deserve a bounded response. Slugs strip punctuation and non-ASCII characters, so distinct normalized names can collide. Generated names also receive no output length check. Validate normalized output and report collisions clearly rather than silently changing meaning. Separately, the backend uses server-local dates while Today displays the browser's date. A first request crossing midnight can also span different captured dates. Use one explicit game date throughout a request and expose the rollover rule, especially before displaying countdowns.

## Recommended changes and choices

Priorities: **P0** means fix before trusting lifecycle decisions. **P1** means the next product improvement. **P2** means worthwhile after those changes. Estimates include focused tests and preserving existing data, but overlap across recommendations and should not be summed mechanically.

### 1. Save and show a real scope

**Priority P1, about 1 to 2 developer days.**

Keep the name field and add an optional short “What should count?” field with an example such as “Disney animated films and their characters, excluding parks and company history.” Normalization must preserve these boundaries. Save the original request alongside an interpreted display name and concise scope. Before the expensive build, show the interpreted scope with Edit and Create controls. For a bare “Disney”, ask the player to choose or describe the intended interpretation instead of guessing.

Use this stored scope in generation, validation, hints and the game host. Put a short scope line on the game introduction and make it accessible from Today. A clearer title such as “Disney Films” helps, but the description carries inclusions and exclusions that cannot fit in a title. Freeze scope once published. A materially different scope should create a new topic, preserving the old games' meaning.

**Why:** scope errors damage the central deduction game. More subjects do not compensate for an unclear answer space.

**Trade-offs and alternatives:** an extra confirmation tap and some additional text on phones. A prompt-only fix is faster and should be included, especially removing the scope-erasing Marvel example, but it cannot infer private intent. A mandatory long questionnaire is unnecessary. I would pick one compact preview with optional clarification, using the current normalization call to prepare it rather than adding a separate speculative capacity call. Do not preview actual future pool subjects, which would spoil puzzles.

### 2. Publish useful difficulties, including limited runs

**Priority P1, about 2 to 3 days with the lifecycle interface.**

Make readiness and availability per difficulty. A topic can be listed when at least one difficulty is ready, with the other's status stated. Topic-level build progress should not hide a completed, usable normal pool just because expert failed.

First remove the coupling while retaining the existing 50-subject floor for each difficulty. This immediately makes Movie Classics normal playable without inventing a new acceptance threshold. Then pilot a **30-subject floor per difficulty** for explicitly limited runs, subject to a manual quality audit. The rationale is a month of daily draws already buffered, not a claim that 30 proves total capacity. On that policy Movie Classics' 41 expert subjects could also be published if they are good. Keep subject-quality rules unchanged.

Under the initial conservative step, a creator might see “Normal is ready. We could not make enough expert puzzles yet.” Under the limited-run pilot, both could be ready with a general notice that some topics eventually finish. Do not assert that Movie Classics is intrinsically narrow or guaranteed to end based on its first expert batch.

**Trade-offs and alternatives:** the interface must support missing difficulties, and smaller starting pools offer less protection against supply errors. Lowering the global 50 threshold alone retains the unhealthy coupling. Always requiring both pools selects for broad topics, contrary to player interests. Repeated top-ups until every topic passes spend more money without proving sustainability. I would allow independent difficulty publication and at most one small targeted top-up for a marginal missing pool, only within a build budget. A topic with neither usable pool receives a specific explanation and an editable scope, never automatic broadening.

### 3. Treat low yield as evidence, not a permanent verdict

**Priority P0, about 1 to 2 days for response integrity and bounded recovery.**

Require a verdict for every submitted candidate, exactly once, referring to that candidate. Reject unknown names, conflicting verdicts and incomplete responses as technical failures. Prefer candidate IDs in the response so punctuation or naming changes do not invent answers. Keep deterministic exact duplicate filtering separate from model judgments. Malformed output must not create a successful zero-yield refill record.

Keep counts for requested, parsed, validated, accepted and actually inserted subjects, plus rejection categories. This lets the operator distinguish short output, duplicates, poor difficulty fit and a genuinely unproductive search.

For a structurally valid refill that inserts fewer than 10, retain its valid subjects and mark that difficulty as low yield. Permit one bounded confirmation attempt using a different subcategory plan or smaller batch. Only **two consecutive valid, low-yield attempts** should move the difficulty into winding down. Label this an operational decision to stop searching, not proof that every possible subject has been found. Provide an operator action to reopen it after a prompt or scope-policy correction.

For network or model-service failures, persist retry eligibility with a small capped backoff, for example three recovery attempts per incident. Do not count these as scarcity evidence. Check low pools at startup and with a lightweight periodic task in the existing process. An empty-pool request must be able to start eligible recovery and report “Preparing more puzzles. Try again shortly.” Once attempts are exhausted, show temporary unavailability and notify the operator, rather than spinning forever or falsely saying the subject space is exhausted.

**Trade-offs and alternatives:** extra state and a few additional cents for confirmation/recovery. The current single-batch cutoff is simple but too sensitive. Infinite retries are unacceptable. A second model could diversify judgments, but is not needed to fix response coverage or the recovery dead end. Keep the 10-subject heuristic provisionally, with two observations and explicit budgets, then tune against measured quality and yield.

### 4. Make winding down and completion understandable

**Priority P1, about 1 to 2 days, shared with recommendation 2.**

Represent difficulty status using a small set of states: building, available, recovering, winding down, finished and unavailable after repeated technical failures. The API should provide the display state, playable-today flag and concise reason. Internal counts and errors belong in operator information, not the normal player flow.

When no more refills are planned, show “Expert is nearing the end of its run” before the pool empties. A count such as “12 fresh puzzles remain” is a count of stock, not a guaranteed calendar end date. Avoid claiming how many subjects remain undiscovered. With one draw per active date, the final pool gives a clear remaining run length in puzzle dates, while skipped dates extend calendar life.

At zero stock, preserve a Play/Resume/Results link if today's puzzle already exists. Only disable starting a new puzzle date. For a finished difficulty, show “Expert has finished. Try Normal or another topic.” Move a fully finished topic out of the main active list into a small finished section, while keeping replays, history and share links intact.

**Trade-offs and alternatives:** extra status copy and a few branches in the two-button UI. Silently hiding topics loses context and can look like deletion. Recycling subjects saves generation but violates the existing avoidance of repeats, especially for experienced friends. I would keep unique runs and clear endings. A separately chosen encore mode could be considered later if players ask, with explicit labeling and repeat rules.

### 5. Remember rejected candidates without making mistakes permanent

**Priority P2, about 1 to 2 days.**

Store candidate, topic, target difficulty, verdict, reason category, generation/validation policy version and timestamp. Retain rejection records across build retries. Exclude stable failures such as nonexistent subjects, duplicates and clearly out-of-scope answers from future proposals under the same scope. Keep difficulty mismatch local to that difficulty, and allow an appropriate candidate to be separately validated for the other pool. Ambiguous or weakly explained rejections should be reviewable and eligible for reconsideration after a policy change.

Do not append an indefinitely growing paragraph of all rejection reasons to every prompt. Begin with compact names and relevant stable exclusions. The accepted history also grows forever, so record exclusion count, prompt size and yield before introducing more complex retrieval. Store records cheaply in SQLite even when they are not all sent to the model.

**Why:** prevents repeated wasted proposals and makes scarcity decisions diagnosable.

**Trade-offs and alternatives:** larger prompts and persistent false negatives if rejection handling is careless. Adding every rejected subject to a permanent topic-wide blacklist is simpler but would unnecessarily shrink both pools. Keeping only aggregate counts is cheaper to implement but cannot prevent repeat proposals. I would choose reason-aware, difficulty-aware records with an operator reset/review path, without embeddings or an external vector database.

### 6. Refund unsuccessful suggestions, bound paid attempts separately

**Priority P1, about 1 day.**

Treat a submitted build as a reserved suggestion slot. If any useful difficulty publishes, it consumes the slot. If none publishes because of technical failure or insufficient acceptable subjects, release it exactly once. Store the reservation's original usage date so a build finishing after midnight refunds the correct day. Dismiss merely hides a failed result and does not change accounting.

Retain a separate attempt cap, including failed builds and scope previews, to protect the operator. Start with a modest configurable allowance such as six build attempts per account per day for the default three successful suggestions, and a low concurrent-build limit. Reuse a recent identical failed result rather than immediately paying to repeat it. Use a build ID for idempotent retries so a phone losing its response can rediscover the accepted request instead of creating another one.

Reserve/check quota and create the accepted build atomically after normalization, rechecking the available allowance at that point. Bound normalization/preview calls independently because a successful-build cap does not cover them. Exact existing-name matches can avoid normalization and provide a direct link, with the normal semantic matching path for other inputs.

**Trade-offs and alternatives:** two counters are slightly more work, and refunded failure attempts still cost money. Counting every attempt is defensible for a larger or abusive audience, but feels unnecessarily punitive here. Unlimited free retries are the opposite mistake. I would refund all unsuccessful builds with a capped attempt budget. Display successful suggestion allowance as the primary concept and explain the attempt cap only when it becomes relevant.

### 7. Close the small reliability gaps without adding infrastructure

**Priority P0 for draw/build correctness, P1 for the rest. About 1 to 2 days.**

Choose the daily subject, remove it from the pool and persist the day's puzzle in one short SQLite transaction before awaiting hint generation. Then backfill hints independently. Never hold a write transaction across a model call. Return the persisted answer if another writer already created that daily puzzle. Reuse a single explicit puzzle date through the request so midnight cannot split drawing and game creation.

At insertion time, recheck accepted history and both pools, using a conservative normalized key for exact aliases where safe. Keep semantic near-duplicate checks in validation. Apply a deliberate allocation rule on every refill, not just the initial build. Normal can retain preference, but records should distinguish expert validation losses from overlap allocation, and replacement expert candidates should stay within the build budget.

On initial build failure, cancel and await sibling tasks, or collect both outcomes and publish their successful pools under independent difficulty status. A failed/retried build should reuse healthy existing pools rather than delete them wholesale. Bind writes to a build ID so an obsolete task cannot mutate a replacement. Startup should resume only unfinished work, and shutdown should cancel/await tasks before closing the database.

Keep a documented single-process deployment for now, consistent with the supplied CLI. Add a small build/refill semaphore so a burst of suggestions does not overwhelm the host model service alongside gameplay. If multiple workers become necessary, replace process-local task ownership with SQLite leases and transactional claims. That is a future requirement, not a reason to adopt Redis today.

Retry status polling on failures, refresh when the page returns to the foreground, show a quiet connectivity message, and check Dismiss responses. Keep the existing useful wait estimate. Do not invent a percentage progress bar for work whose duration is unknown. Validate normalized names and handle slug collisions explicitly.

**Trade-offs and alternatives:** transactions and task cleanup require a few targeted failure tests. Generating hints before recording the puzzle keeps one apparent operation but exposes the crash window. Moving all jobs to a separate queue service would add deployment work out of proportion to this audience. I would keep the current architecture and make its state transitions reliable.

### 8. Improve quality based on evidence, preserve inexpensive defaults

**Priority P2, about half a day for sampling and 1 day for basic operator reporting.**

Add explicit validation criteria for factual existence, a uniquely identifiable answer, sufficient stable facts for yes/no questioning, and fit with the saved scope. Expert should mean knowledgeable players have a fair chance, not merely the most obscure strings the model can produce. Review samples manually before deciding whether the model or prompts need changing.

Track build/refill duration, actual token usage when available, attempts, failure causes and good subjects inserted. Show the operator low-pool and stuck-build summaries through the existing developer surface or a simple query/report. A player “Report this puzzle” action with a small reason list would provide direct evidence of off-topic, ambiguous or incorrect answers without requiring review of every generated subject.

**Trade-offs and alternatives:** manual review costs operator time, while universal stronger-model validation increases latency and cost without proving better player outcomes. I would keep the configured inexpensive model, use targeted review for disputed topics and compare alternatives only if the samples show recurring errors. Keep 100-subject production batches and the below-50 refill trigger initially. Both can be tuned later, but their precise values are less urgent than misleading scope and unreliable exhaustion.

Schema changes across these recommendations need small additive migrations that preserve games and pools. The current [database documentation](docs/database.md:115) describes schema changes by recreation. Resetting a live friends-and-family game to introduce lifecycle fields would lose useful history and should not be the rollout plan.

## What to measure or test before settling policy

### Product decisions

- **Scope comprehension:** ask a few existing players what they think “Disney”, “Marvel”, “Movie Classics” and one precise topic include, then show the proposed preview. Check whether they can predict in-scope answer types. This is more useful here than a large A/B test. Never expose real future puzzle answers in the preview.
- **Value of independent difficulties:** ask whether players would enjoy Movie Classics normal even without expert, and inspect actual normal/expert starts, completion, wins and hint use. If almost nobody plays expert, do not devote equal replenishment effort to both.
- **Finite-run expectations:** try the winding-down and finished copy on a phone. Verify people understand that other players do not consume their stock, that today's shared puzzle stays accessible, and that a topic ending is different from the AI service being unavailable.
- **Starting stock:** compare the existing 50 floor with a 30-subject limited-run pilot. The decision depends on subject quality, accepted stock, recovery performance and whether players welcome shorter runs. Do not lower validation standards to pass either threshold.

### Generation and capacity

- Repeat several bounded generation trials for narrow and broad topics at accepted exclusion sizes near 0, 100, 150, 200 and beyond. Match production's **combined pooled and drawn subjects across both difficulties**, batch size, concurrent initial build and overlap allocation. Compare smaller batches or subcategory-directed retries only within a fixed total call budget.
- Record rejection categories, repeated rejected candidates, malformed-response rate, overlap removal, actual insertion counts, cost per usable subject and manual quality judgments. These distinguish actual scarcity from prompt saturation, incomplete output and overly strict difficulty labeling.
- Separate valid low-yield batches from technical failures when estimating whether a second low-yield attempt is sufficient. A retained count is evidence of stock, not a statistical estimate of every possible subject in the topic.
- Audit representative accepted and rejected subjects for factuality, topic fit, duplicates and guessability, including the observed 96/41 Movie Classics and 63 expert World Geography outcomes if their original subjects are available. Those numbers alone cannot establish puzzle quality.

The existing [generation experiment tool](src/h21/generate.py:115) is useful but **does not reproduce production policy**. It defaults to batches of 25, excludes all generated subjects including rejections, and stops after two half-rejected batches. Production requests 100, forgets rejected candidates and stops refilling after one insertion count below 10. Its findings should guide hypotheses, not be treated as exact production lifetime forecasts.

### Reliability and accounting

Before releasing changes, use deterministic mock-model scenarios for:

1. Unknown KEEP names, missing verdicts, duplicated/conflicting verdicts, truncated responses and wrong-difficulty candidates. None should falsely signal exhaustion or insert an unsubmitted subject.
2. A background outage followed by the last stock being drawn, a restart at zero stock, and later recovery. Today's existing puzzle must still work and an empty eligible pool must be able to restart replenishment.
3. One valid low-yield attempt followed by a productive attempt, then two valid low-yield attempts. Only the latter should wind down, and good subjects from every valid attempt must remain usable.
4. Normal succeeding while expert fails, overlap pushing expert below the floor, and simultaneous refills proposing the same subject. Preserve the healthy pool and enforce the chosen allocation consistently.
5. Restart or cancellation during hints, midway through a two-difficulty build, and after recording a pool insertion but before recording its refill outcome. Confirm no subject loss, incorrect lifecycle decision or obsolete-task write.
6. Concurrent submissions at the last quota slot, retries after lost HTTP responses, and builds spanning the daily boundary. Count attempts and reservations correctly, refund once, and never erase another creator's build status on a retry.
7. A poll fetch failure, phone backgrounding, failed Dismiss, and a first game request crossing the date boundary. The interface should recover and all game records should refer to the same chosen date.

The existing [pool tests](tests/test_puzzle_pool.py:1) cover useful database behavior and generation line parsing, but do not exercise these asynchronous lifecycle or validator-coverage cases. Add focused tests when implementing those changes, rather than a broad new test framework.

## Local checks performed for this review

I exercised selected existing functions using temporary SQLite storage and mock responses, with no application startup, paid calls or source edits:

| Check | Observed result |
|---|---|
| Validator receives unparseable prose | Returns an empty results list instead of raising a technical error. |
| Validator says KEEP for a name absent from its submitted batch | Accepts that name as a kept result. |
| Last subject is drawn, before the daily puzzle is recorded | Pool is empty and the subject is absent from the known-solutions exclusion list. This confirms the crash window. |
| Empty ready pool has a previous successful refill record | Daily draw raises 503 without invoking the background refill trigger. |
| Latest refill record has zero insertions | Exhaustion guard returns true, regardless of why zero subjects were inserted. |

These are targeted function checks, not a full application or browser test. Cross-process races, paid-model quality, true topic capacity and real-world error frequency remain unmeasured.

## Suggested order

First fix validator coverage, atomic drawing and empty-pool recovery so existing topics do not acquire false endings. Next ship scope confirmation, independent difficulty readiness and lifecycle copy together, with fair bounded suggestion accounting. Then add rejection memory and lightweight measurements, and use those results to decide the 30-subject pilot, batch tuning or model changes.

The intended outcome is modest: a creator knows what they are asking for, good puzzles can publish without a matching expert pool, temporary failures recover, and a finite topic finishes clearly while its history stays intact.
