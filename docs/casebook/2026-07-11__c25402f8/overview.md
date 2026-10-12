# Puzzle generation overhaul: batch pool with validation

## Problem

The current puzzle generation system creates one subject at a time via LLM when the first player starts a game for a given (topic, difficulty, date). This has three issues:

1. **First-come bias**: New topics always get the most obvious subjects first (e.g. "Marie Curie" for Notable People) because the LLM defaults to the most prominent answer when the exclusion list is empty.
2. **Degrading consistency**: As the exclusion list grows, the LLM is forced into increasingly obscure territory even for "normal" difficulty, making difficulty inconsistent day-to-day.
3. **Momentum**: Each generation sees the previous solutions, so one category snowballs. Israeli History produced a week of consecutive prime ministers.
4. **Fragile dedup**: Relies entirely on the LLM reading a growing text list and not repeating -- no structural guarantee.

## Solution

Replace on-demand single-subject generation with a pre-generated pool:

1. **Batch generation**: Generate 100 subjects per (topic, difficulty) in one LLM call, stored in a `puzzle_pool` table.
2. **Validation step**: A second LLM call reviews each batch for topic relevance, difficulty appropriateness, and duplication (KEEP/REJECT with reasons).
3. **Random draw**: When a puzzle is needed, draw randomly from the pool rather than generating sequentially.
4. **Background regeneration**: When the pool drops below a low threshold (50), kick off a background `asyncio.create_task` to top it up. Refill is triggered by running low, not by running empty, so players never wait on generation except for the very first draw of a new (topic, difficulty), when the pool is empty.

## Design decisions

- **Keep `normal`/`expert` difficulty** (not `easy`/`medium`/`hard`) to avoid fragmentation and choice paralysis.
- **No classifier**: Generate directly per difficulty with guidance in the prompt, rather than generating undifferentiated subjects and classifying after. The batch size + random draw solves the first-come bias without needing a separate classification step.
- **Plaintext over JSON**: LLM returns one subject per line instead of a JSON array. Simpler and more reliable.
- **Lazy hint generation**: Hints are still generated when a game starts, not at batch time.
- **Separate tables**: `puzzle_pool` holds undrawn subjects, `daily_puzzles` holds used ones. Drawing deletes from pool and inserts into daily_puzzles. Exclusion list for regeneration is the UNION of both tables (across both difficulties for a topic).
- **Pool lifecycle**: generate batch -> validate -> store in pool -> draw randomly -> record in daily_puzzles. Pool row is deleted on draw.
- **Exhaustion detection (CLI tool)**: If 2 consecutive batches have >= 50% rejection rate, stop. The server uses a different interim guard (see integration decisions).
- ~~Fallback to single-subject generation~~ and ~~inserting unvalidated batches on validation failure~~: both dropped in the relaunch integration (see below).

## Implementation

All work is on the `puzzle-pool` branch.

### Files changed

| File | Changes |
|------|---------|
| `src/h21/db.py` | New `puzzle_pool` table migration. New methods: `draw_random_from_pool()`, `pool_count()`, `get_all_known_solutions()`, `insert_pool_subjects()`, `clear_pool()`. |
| `src/h21/llm.py` | New prompt templates: `GENERATE_SOLUTION_BATCH_PROMPT_TEMPLATE` (plaintext, one per line), `VALIDATE_SOLUTION_BATCH_PROMPT_TEMPLATE` (KEEP/REJECT with reasons). New dataclasses: `BatchResult`, `ValidationResult`, `ValidationBatchResult`. New functions: `generate_solution_batch()`, `validate_solution_batch()`, `_parse_line_per_subject()`. |
| `src/h21/main.py` | Rewritten `get_today_solution()` to draw from pool. New functions: `_maybe_regenerate_pool()`, `_regenerate_pool()`. Constants: `POOL_BATCH_SIZE=100`, `POOL_LOW_THRESHOLD=50`. Module-level `_pool_regeneration_tasks` set to prevent duplicate concurrent regenerations. |
| `src/h21/generate.py` | New CLI evaluation tool (`h21-pool` entry point). |
| `pyproject.toml` | New `h21-pool` console script entry point. |

### CLI evaluation tool (`h21-pool`)

A standalone tool for evaluating the generation and validation prompts without touching the database. Usage:

```
h21-pool "Notable People" --difficulty normal --count 50 --batch-size 25
h21-pool "World Geography" --difficulty expert --count 100 -o results.txt
h21-pool "Notable People" --count 50 -e previous-run.txt -o new-run.txt
```

- `--exclude/-e`: Seed exclusion list from a file (one subject per line)
- `--output/-o`: Write accepted subjects to file (one per line, chainable as input to next run)
- All LLM responses (generation + validation) and the summary print to stderr
- Exhaustion detection: stops after 2 consecutive batches with >= 50% rejection

## Status

- Integrated for the relaunch and running on the lab (red slot) with a fresh database. Rebased onto master on 2026-10-10. To be merged into a new `dev` branch (created from master), not master, since this is a clean relaunch.
- Evaluated against a live LLM and looks good on variety, difficulty and validation parsing (see below).

### Evaluation run (2026-10-10)

`h21-pool "Israeli History" --difficulty normal --count 100` with `gpt-6-luna`, reasoning effort `medium`, default CLI batch size 25. Five batches, about 1m40s, 105 kept and 20 rejected.

- **Variety**: good spread across modern leaders, wars and accords, ancient history, pre-state militias, institutions and cities. Prime ministers are 12 of 105, so the momentum problem is gone.
- **Validation**: parses cleanly. 18 of 20 rejections were "too obscure for normal", some arguably wrong for the likely audience (e.g. Moshe Sharett, a prime minister).
- **Weak keeps**: a few abstract subjects make awkward 21-questions answers ("Zionism", "Aliyah", "The 1950s Israeli austerity period").

### Batch-size comparison (2026-10-10)

19 runs of `h21-pool --count 100` with `gpt-6-luna`/`medium`: five topics (Israeli History, Notable People, World Geography, Space Exploration, The Beatles) at normal difficulty with batch sizes 25, 50 and 100, plus Israeli History and Notable People at expert with 25 and 100. Logs and kept lists are in `/tmp/h21-pool-eval/runs/` (ephemeral).

- **Batch size barely matters for quality.** Generators returned the requested count (98-100 for size 100), no exact duplicates in any run, and similar category spread (Israeli History prime ministers: 12/101 at 25, 11/129 at 50, 10/115 at 100).
- **Depth into the topic is what drives rejection, not batch size.** First batches keep 80-100% for most topics at any size. Rejection climbs as the exclusion list grows past roughly 100 subjects, almost all as "too obscure": Israeli History normal kept 82/99 then 33/98 at size 100, and 23/25 falling to 17/25 at size 25. Space Exploration is shallowest (55/100 kept on the first size-100 batch, 13/25 by the fifth size-25 batch). Broad topics (Notable People, World Geography) barely reject at all past 200.
- **Larger batches are cheaper and faster** (fewer calls, the exclusion list is sent fewer times). Wall time per run was similar or lower at size 100.
- **The CLI exhaustion rule never fired**, even when Space Exploration batches hovered around 50% rejection. As a running-dry signal, the per-batch keep rate is informative but noisy around the threshold.
- The CLI overshoots `--count` because it adds a whole validated batch at once (e.g. 195 kept for a count of 100).

**Conclusion**: keep the server's `POOL_BATCH_SIZE=100`. A narrow topic's normal-difficulty capacity is on the order of 100-150 subjects, i.e. a few months of daily puzzles, so running dry is a realistic event for user-submitted topics.

## Decisions from evaluation

- **Keep batch size 100** on the server (see batch-size comparison).
- **Trust the validator's difficulty calls.** Its "too obscure for normal" rejections (e.g. Moshe Sharett) were judged acceptable; no tuning of the obscurity bar.

## Relaunch integration (2026-10-10)

The app never gained traction, and the few accounts are family and friends, so all game data will be wiped at relaunch. That freed the integration from backwards compatibility.

- **No migrations.** The 21 migration methods were collapsed into one `CREATE TABLE IF NOT EXISTS` schema (taken from a freshly created database). Old databases are unsupported.
- **The pool is the only puzzle source.** The single-subject generator and its prompt are deleted. Unvalidated subjects never enter the pool: a failed generation or validation call adds nothing.
- **Topic status** (`generating`, `ready`, `failed`, plus a user-facing `status_detail`). Creating a topic returns immediately and builds both difficulty pools in the background, concurrently, then removes expert subjects that duplicate normal ones. Only the creator sees a topic before it is ready; the home page shows the animated brand mark with "Creating puzzles…" and polls `/api/topics` every 4s. A failed topic shows its reason and a Dismiss button (`DELETE /api/topics/{slug}`), and anyone may suggest the same name again. Builds interrupted by a restart, and the seeded default topics, are built at startup.
- **New-topic threshold: 50 kept subjects at every difficulty**, separate from the refill threshold (also 50). Rejection of the whole topic if either difficulty falls short.
- **Interim exhaustion guard**: every successful refill is logged in `pool_refills`; once a refill keeps fewer than 10, that pool is not refilled again, and when it empties the topic answers 503 "This topic has run out of puzzles." The real design (notice in the app, maybe a "running low" warning) is still open.
- **Per-puzzle draw lock**, so concurrent first players of the day share one draw instead of racing.
- **Background tasks are strongly referenced** (the branch's `asyncio.create_task` results could be garbage collected mid-flight).
- **Lab verification**: World Geography, Notable People and The Beatles each built in about a minute (normal 94-99 kept, expert 74-91); "Left-Handed Accordion Makers from Moldova" was rejected with 0 kept; a game drew from the pool; dismissal worked.
- Parser fix: list markers are only stripped when followed by whitespace (so "2001: A Space Odyssey" survives) and curly quotes are stripped.

## Open items

Closed. The pool overhaul is done and merged; the remaining items (expert threshold, running dry, rejected subjects, turned-down topics costing a suggestion, pool visibility) moved to the topic flow case (60ac), together with the topic preview idea from the UI overhaul case.
