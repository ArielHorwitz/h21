# H21 topic flow review

## Summary of top recommendations

1. **Stop the generator from quietly lying to the rest of the system (P1, small).** One malformed validator reply can permanently retire a healthy pool or fail a good topic, and nothing in code stops a previously used subject from being served again. Check that the validator's reply covers the batch, match its output back to the generated list, dedupe against history in code, store rejected subjects, and require two weak refills in a row before declaring a pool exhausted.
2. **Fix topic scope at the door (P1, small now, medium later).** The normalizer prompt literally teaches the model to drop qualifiers (`"marvel movies and comics" -> "Marvel"`). Fix that example today. Then add a cheap preview step: normalized name, one-line scope, a few sample subjects, and narrower alternatives when the name is ambiguous, before the build starts and before quota is spent.
3. **Make running out a normal, visible end of life instead of an error (P1, small to medium).** The system already knows about 50 plays in advance that a pool is ending. Show per-difficulty availability on Today, a "final N puzzles" badge, and a "finished" state instead of a 503 behind a play button.
4. **Rescue near-miss topics instead of rejecting them (P2, small).** Before rejecting, run one top-up batch for the short difficulty. If expert is still short but normal is healthy, launch normal-only. Movie Classics (96 normal) should have shipped.
5. **Refund the suggestion quota when a build fails (P2, small)**, with a separate attempts ceiling so refunds can't become an unbounded spend loop.

Things I would leave alone: build latency, model cost, recycling old subjects, and topic moderation (beyond a dev-only delete).

A recurring theme: the 50-subject gate is strict mostly because ending is ugly. Once running out is graceful (item 3), it becomes safe to accept shallower topics (item 4), and that also resolves the contradiction where players are told "try something broader" while broad names are what cause the Disney problem.

---

## 1. The current flow, end to end

Paths below are relative to the repo root.

**Suggest** (`static/suggest.js:137`, `src/h21/main.py:1294`)
1. Player types a name on the Suggest page and taps Create. No preview or confirmation.
2. Server checks the daily quota (`daily_topic_limit`, default 3 per `src/h21/config.py:66`. Note that `docs/database.md` still says 1).
3. One LLM call normalizes the name into a clean English title (`src/h21/llm.py:152`). The slug is derived from it.
4. If the slug exists and is not `failed`, return 409. If it exists and is `failed` (anyone's), it is deleted and rebuilt under the new creator.
5. Topic row inserted as `generating`, quota counter incremented, background build started. The creator sees the normalized name for the first time in the success message.

**Build** (`src/h21/main.py:376`)
6. Both difficulties run concurrently. Each is one generation call (100 subjects) and one validation call over the same 100 (`_refill_pool`, `src/h21/main.py:314`). The exclusion list is every known subject for the topic, both difficulties, used and pooled.
7. Kept subjects (as echoed back by the validator) are inserted with `INSERT OR IGNORE`. A `pool_refills` row records `generated` and `inserted`.
8. Expert subjects that also landed in the normal pool are deleted (exact string match, count discarded).
9. If either pool has fewer than 50, the topic is `failed` with "Not enough puzzles could be made for this topic. Try something broader." Any exception gives `failed` with "Something went wrong". Otherwise `ready`.
10. Creator's Suggest and Today pages poll every 4s and show "Creating puzzles…", then play buttons or a failure message with Dismiss. Other players only ever see `ready` topics.

**Daily play** (`src/h21/main.py:276`)
11. The first player of a topic+difficulty on a given day draws a random subject from the pool (deleting it), generates 5 hints, and records the daily puzzle. Days with no players consume nothing.
12. After a draw, if the pool is under 50 and no refill is in flight, a background refill runs (same generate+validate as above).

**End of life**
13. If the latest refill inserted fewer than 10, no further refills ever happen (`src/h21/main.py:337`). The pool drains over about 50 more plays.
14. When it is empty, starting a game returns 503 "This topic has run out of puzzles", shown as an error on the game page (`static/game.js:185`). The topic stays `ready`, stays on Today with both buttons, and fails the same way every day after.

**Seeded topics** (`src/h21/db.py:171`): Notable People and World Geography are inserted as `generating` with no owner and go through the same build and the same 50-subject gate on first boot.

---

## 2. Problems and risks

Severity is about impact on this audience (a small group of friends and family, on phones), not abstract worst case.

| # | Problem | Who it hurts | Severity |
|---|---------|--------------|----------|
| P1 | **One bad validator reply permanently kills a pool.** Lines that don't start with `KEEP `/`REJECT ` are logged and dropped (`src/h21/llm.py:375`). If the model formats its reply as `1. KEEP …`, `- KEEP …` or `**KEEP**`, the refill records 0 inserted, and the `< 10` latch stops all future refills with no way to reset short of SQL. At build time, the same failure rejects a good topic as "too narrow" and blames the user. | All players of that topic, the creator | High (silent, irreversible, misattributed) |
| P2 | **Repeat puzzles are possible.** The pool's `UNIQUE` only covers subjects currently in the pool. Used subjects live in `daily_puzzles`, and the only guard against re-adding them is the validator noticing them in a long exclusion list. Refills also don't run the cross-difficulty cleanup, so a subject can enter both pools. Minor variants ("The Eiffel Tower" vs "Eiffel Tower") pass every check. | Regular players, who will notice a repeat answer | Medium-high (visible quality bug, gets likelier as the exclusion list grows, which is exactly when the validator is weakest) |
| P3 | **The validator's output is trusted as the subject list.** `kept_subjects` comes from the validator's echoed names, not the generator's list, so a renamed or hallucinated "KEEP" line (including one copied from the exclusion list) goes straight into the pool. | Players | Medium |
| P4 | **Scope drift from the normalizer.** The prompt example `"marvel movies and comics" -> "Marvel"` actively trains qualifier removal. The topic name is then the only spec that generation, validation, hints and the host ever see. Whether "Disney" was typed or "Disney movies" was collapsed, nothing shows the creator what they're getting before a minute-long build. | Creator (disappointment), every player of that topic | High for satisfaction, the observed Disney case |
| P5 | **Contradictory guidance.** Failure says "Try something broader", but broad names are what cause scope drift. Movie Classics failed on expert alone, yet the message implies the whole topic was too narrow. | Creator | Medium |
| P6 | **The narrowness gate measures one noisy sample, not topic depth.** It's one batch of 100 per difficulty, with one judge. Expert runs systematically lower (Movie Classics 41, World Geography 63), partly from prompt calibration, partly from the cross-difficulty purge (whose size isn't logged). A topic with 96 good normal puzzles, about three months of play, is thrown away because of expert. | Creators, everyone who would have played it | Medium-high |
| P7 | **Exhaustion is a cliff.** No warning, topic stays listed, both buttons stay active, every tap is a 503 error page. Also per-difficulty: normal can be dead while expert lives, and the UI can't express that (`static/home.js:180` always renders both buttons). | All players, daily, indefinitely | High (it's the end state of every narrow topic, and it looks like a bug) |
| P8 | **Exhaustion latch is too twitchy and has no memory of rejections.** A single refill under 10 ends a pool forever. Rejected subjects aren't stored, so each refill re-proposes known rejects, inflating the rejection rate that then trips the latch. The `h21-pool` eval CLI uses a different, more robust rule (batches of 25, rejected subjects added to exclusions, stop after two poor batches, `src/h21/generate.py:184`), so the experiments behind the "about 100 to 150 subjects" estimate don't reflect production behavior. | Players of mid-depth topics, operator's understanding of the system | Medium |
| P9 | **Failed builds cost quota**, including "Something went wrong" failures that are entirely the server's fault. With 3 a day, one transient OpenAI error eats a third of the day's allowance, and the failure message invites a retry that costs another. | Creator | Medium (feels unfair, discourages suggesting) |
| P10 | **Transient errors become permanent failures.** No retry inside the build. One 429 or connection blip fails the topic. | Creator | Medium |
| P11 | **Seeded topics can fail invisibly and permanently.** They have no owner, so a `failed` seeded topic is shown to nobody, can't be dismissed, and isn't retried on restart (only `generating` is resumed). World Geography expert at 63 is not far above the gate. A first boot during an API hiccup leaves the app with zero topics. | Everyone, at deploy time | Medium (rare, but total) |
| P12 | **No observability.** Rejection reasons, raw responses, cross-difficulty removal counts and token usage are all discarded. `pool_refills` has counts only. There is no view of pool runway per topic. The operator can't tell saturation from prompt failure. | Operator | Medium (blocks good decisions on everything above) |
| P13 | Re-suggesting someone else's failed topic deletes their failed card and reassigns it. A `generating` topic returns "Topic already exists" to other users, who then can't find it. Near-duplicate topics ("World War II" vs "Second World War") are separate. | Creators | Low |
| P14 | Schema changes have no migration path (`docs/database.md`: edit and `h21-reset`). Several fixes below want a column. | Operator | Low now, real once the DB has history worth keeping |
| P15 | No tests cover the build gate, refill latch, quota or create/dismiss flow. `tests/test_puzzle_pool.py` only tests DB helpers. The `LLMClient` Protocol makes a fake client easy. | Operator | Low-medium |

Not problems, in my reading: build latency (a minute with a clear "creating" state and polling is fine), model cost (cents, and refills happen roughly every 50 plays), and the lazy draw (it means topics only age when played, which stretches narrow topics further than "a few months" for a small audience).

---

## 3. Recommendations

Effort: **S** is under half a day, **M** is one to two days, **L** is more. Priority: **P1** do now, **P2** do soon, **P3** when convenient.

### R1. Harden the generate/validate step (P1, S)

Fixes P1, P2, P3, part of P8.

What to do, all inside `_refill_pool` and `validate_solution_batch`:
- **Coverage check.** If the validator's parsed results cover less than about 80% of the submitted subjects, raise `LLMError` instead of recording a refill. A malformed reply then behaves like a transient failure (retried later) rather than a verdict. Also make the parser tolerant of list markers, reusing `_LIST_MARKER_PATTERN`.
- **Match back to the batch.** Only accept KEEP lines whose subject matches a generated subject after normalization (casefold, strip punctuation and a leading "the/a/an"). Insert the generator's spelling.
- **Code-side dedup.** Before inserting, drop anything whose normalized form matches any known solution for the topic in either difficulty (used, pooled, or rejected-for-this-difficulty). This makes repeats impossible regardless of how well the model reads a 500-line exclusion list.
- **Persist rejections** in a new `pool_rejections(topic_slug, difficulty, subject, reason, rejected_at)` table. Add them to the *generator's* exclusion list for that difficulty only (a "too obscure for normal" reject may be a fine expert subject). Don't add them to the validator's exclusion list, where they'd read as duplicates.
- **Two-strike exhaustion.** Treat a pool as exhausted only after two consecutive refills insert fewer than 10, matching what the eval CLI already does. Give the dev panel a way to clear the latch.

Trade-offs: generator prompts grow by the rejection list (more tokens, still cents). Fuzzy normalization can over-merge ("Paris" the city vs "Paris" the myth figure) on rare occasions, which costs one subject, which is acceptable. A new table needs no migration, since `CREATE TABLE IF NOT EXISTS` handles it.

Alternative considered: a stronger "dedup" prompt or a second validator pass. Rejected: deterministic code is cheaper and actually guarantees the property.

### R2. Fix scope at the point of suggestion (P1 for step a, P2 for step b)

Fixes P4, P5.

**a. Normalizer prompt (S, do today).** Replace the `"marvel movies and comics" -> "Marvel"` example with ones that preserve scope: `"disney movies" -> "Disney Films"`, `"marvel movies and comics" -> "Marvel Films and Comics"`. Add an explicit rule: keep qualifiers that narrow the topic, only fix language, spelling and casing.

**b. Preview and confirm (M).** Add `POST /api/topics/preview` that, in one LLM call, returns the normalized name, a one-sentence scope ("Feature films released by Walt Disney Studios, live action and animated"), five sample subjects, and, if the name is ambiguous, two or three narrower alternatives. The Suggest page shows this as a card with the alternatives as tappable chips and a Create button. Quota is spent only on Create.

Alternatives:
- *Post-build review*: build, show the creator real subjects, and let them discard before it goes public. More accurate (real data) but costs a full build and a minute's wait per iteration. Worse on phones, where people won't wait around to iterate.
- *Store the scope line and feed it to every prompt* (generation, validation, hints, host). This is the most powerful version because it makes the whole pipeline agree on what the topic means, and the host can answer "Is it a film?" with the right frame. It needs a `topics.description` column, so either a small `ALTER TABLE` guard in `ensure_schema` or a reset (see P14). I'd do this together with (b), since the preview already produces the line, but it can follow later.
- *Do nothing beyond (a)*: defensible. Some players may enjoy "Disney" spanning films, parks and executives, since 21 questions copes fine with "Is it a person?". The real harm is only expectation mismatch, and (a) removes the self-inflicted part.

My pick: (a) now, (b) plus the stored scope line next. Rate-limit previews lightly (they're unmetered LLM calls).

Also change the failure copy: say which difficulty fell short, and stop saying "broader" (see R4, which makes this rare anyway).

### R3. Make the end of a topic graceful (P1, S to M)

Fixes P7.

- **Per-difficulty availability** (S). Have `get_topics_ranked` return, per difficulty, whether it's playable today (today's puzzle exists or the pool is non-empty). Today renders an unavailable difficulty as a disabled "All played" pill. When both are gone, mark the topic `retired` (status is free-form TEXT, no schema change) and move it to a collapsed "Finished topics" section, or drop it from Today.
- **Runway notice** (S). The latch trips when about 50 subjects remain, so the system knows well ahead. When a latched pool has 14 or fewer left, show "Final N puzzles" on the topic card. Tell the creator on their Suggest page. A small sense of occasion, and a nudge to suggest a follow-up topic.
- **No 503 on the happy path.** Keep the server check, but the UI should never send a player to a dead end.

Alternatives considered:
- *Recycle old subjects after N months.* Rejected for now: a small, repeat audience remembers answers, and replays/history expose them. Revisit only if topics run out much faster than new ones arrive.
- *Auto-extend into a "sequel" topic.* Interesting but premature. The runway notice plus easy suggesting covers it.

### R4. Rescue near-miss builds (P2, S, but the normal-only part depends on R3)

Fixes P6, P5.

- **Top-up before rejecting.** If a difficulty lands under 50, run one more refill for that difficulty (now excluding rejects, per R1) before judging. Cost: one more pair of calls, about 30 to 60s added only on shortfall. Likely enough for Movie Classics expert (41).
- **Normal-only launch.** Gate on normal only. If expert ends up under a lower bar (say 20), launch without expert, using the per-difficulty availability from R3. A 96-subject normal topic is three-plus months of play.
- **Log the cross-difficulty purge count** so we know how much of the expert shortfall is self-inflicted.

Alternative: just lower `TOPIC_MIN_SUBJECTS` to 30. Simpler, but it ships fragile expert pools that hit the latch quickly, and it doesn't distinguish "deep topic, unlucky batch" from "genuinely shallow". I prefer the top-up.

Once R3 lands, I'd also lower the normal threshold to around 30. With a graceful ending, a one-month topic is a fine thing for friends to have.

### R5. Refund quota on failure, retry transient errors (P2, S)

Fixes P9, P10.

- Wrap each `_refill_pool` call in the build with two retries and backoff for `LLMError`. Most "Something went wrong" failures should disappear.
- On any failure, decrement the creator's `topic_suggestions_used` for the creation date.
- Add a separate daily attempts ceiling (around 10) so refunds can't become an unbounded loop paid by the operator. Not a real threat with this audience, but it's one counter.

Alternative: refund only server-side failures, not "too narrow". I'd refund both. The app told them to try again, and charging for that is hostile, and the cost is cents.

### R6. Seeded topics: bypass the gate and retry (P3, S)

Fixes P11. Seeded topics (no `user_id`) skip the narrowness check, and on startup any ownerless `failed` topic is reset to `generating` and rebuilt.

### R7. Observability and a measurement-ready eval tool (P2, S)

Fixes P12, part of P8.

- Store rejection reasons (comes free with R1's table), purge counts, and `response.usage` token counts per call. Add `inserted`, `rejected` and `unparsed` to `pool_refills` (new columns, see P14), or log them.
- A saved "pool health" query in the control panel: per topic and difficulty, remaining, latched or not, plays per week, estimated days of runway.
- Make `h21-pool` exercise the production path (`_refill_pool`'s batch size, exclusion rules and latch) or at least default to the same parameters. Right now the experiments and production differ (batch 25 vs 100, rejects excluded vs not), so conclusions don't transfer.

### R8. Small things (P3)

- Return the existing topic's slug on 409 so the Suggest page can link to it (P13).
- Don't let a re-suggestion delete someone else's failed topic. Just let the new creator build under a fresh row once the old one is dismissed, or transfer it visibly (P13).
- Introduce a minimal migration step (a list of `ALTER TABLE` statements guarded by `PRAGMA table_info`) before the first column change. It's about 20 lines, and resets will hurt once there's real history (P14).
- Tests with a fake `LLMClient` for: build gate, top-up, latch, coverage-check failure, refund, retired state (P15).
- Optional: a "New, suggested by X" tag on Today for a topic's first few days. Cheap social glue for this audience.

### Leave alone

- **Build latency.** A minute with a clear state and background polling is fine. Splitting into smaller parallel batches would cut it but adds complexity for little gain.
- **Model cost.** Cents per build, refills every ~50 plays. Log usage (R7) and stop worrying.
- **Topic moderation.** Friends and family. A dev-only delete in the control panel is enough.

---

## 4. Measure or test before deciding

1. **Why does rejection climb past ~100 used?** Break rejections down by reason (duplicate, off-topic, wrong difficulty, vague) against exclusion-list size. If duplicates dominate, it's the model failing to follow a long list, and R1's rejection memory plus smaller batches will extend topic life a lot. If difficulty or off-topic dominate, it's real saturation, so accept it and lean on R3.
2. **How noisy is the gate?** Build Movie Classics, World Geography and a couple of borderline topics five times each and record kept counts per difficulty. If the same topic swings across 50, the gate is a coin flip and R4's top-up is clearly justified. Also measure how much the cross-difficulty purge removes.
3. **Validator format failures.** Count how often a reply has unparsed lines or covers less than the full batch, in logs or by replaying. This sizes P1.
4. **Existing repeats.** Query `daily_puzzles` for normalized duplicates per topic, including across difficulties. Any hit confirms P2 in production.
5. **Actual play rate per topic.** Puzzles only draw when played, so runway in calendar days depends on this. It decides how urgent R3 is and what the "final N" threshold should be.
6. **Normalizer regression set.** About 30 realistic inputs ("disney movies", "pixar", "90s sitcoms", "ww2 pacific", non-English) through the old and new prompt, checking that qualifiers survive. Cheap, and reusable for the preview step.
7. **Expert calibration.** Win rate and questions-to-win on expert vs normal. If expert is rarely solved, the validator's expert bar is too high, which also explains low expert yields, and loosening the guidance may fix both.
8. **Preview usefulness (after R2b).** How often creators pick an alternative chip or edit the name. If almost never, the preview can be slimmed down to the name and sample subjects.
