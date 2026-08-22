# Puzzle generation overhaul: batch pool with validation

## Problem

The current puzzle generation system creates one subject at a time via LLM when the first player starts a game for a given (topic, difficulty, date). This has three issues:

1. **First-come bias**: New topics always get the most obvious subjects first (e.g. "Marie Curie" for Notable People) because the LLM defaults to the most prominent answer when the exclusion list is empty.
2. **Degrading consistency**: As the exclusion list grows, the LLM is forced into increasingly obscure territory even for "normal" difficulty, making difficulty inconsistent day-to-day.
3. **Fragile dedup**: Relies entirely on the LLM reading a growing text list and not repeating -- no structural guarantee.

## Solution

Replace on-demand single-subject generation with a pre-generated pool:

1. **Batch generation**: Generate 100 subjects per (topic, difficulty) in one LLM call, stored in a `puzzle_pool` table.
2. **Validation step**: A second LLM call reviews each batch for topic relevance, difficulty appropriateness, and duplication (KEEP/REJECT with reasons).
3. **Random draw**: When a puzzle is needed, draw randomly from the pool rather than generating sequentially.
4. **Background regeneration**: When pool drops below 50, kick off a background `asyncio.create_task` to refill.

## Design decisions

- **Keep `normal`/`expert` difficulty** (not `easy`/`medium`/`hard`) to avoid fragmentation and choice paralysis.
- **No classifier**: Generate directly per difficulty with guidance in the prompt, rather than generating undifferentiated subjects and classifying after. The batch size + random draw solves the first-come bias without needing a separate classification step.
- **Plaintext over JSON**: LLM returns one subject per line instead of a JSON array. Simpler and more reliable.
- **Lazy hint generation**: Hints are still generated when a game starts, not at batch time.
- **Separate tables**: `puzzle_pool` holds undrawn subjects, `daily_puzzles` holds used ones. Drawing deletes from pool and inserts into daily_puzzles. Exclusion list for regeneration is the UNION of both tables (across both difficulties for a topic).
- **Pool lifecycle**: generate batch -> validate -> store in pool -> draw randomly -> record in daily_puzzles. Pool row is deleted on draw.
- **Exhaustion detection**: If 2 consecutive batches have >= 50% rejection rate, stop regenerating (topic is running dry at that difficulty).
- **Fallback**: If pool is empty and batch generation fails, fall back to single-subject generation (existing code path).
- **Validation failure graceful degradation**: If the validation LLM call fails, insert the unvalidated batch rather than losing the generation.

## Implementation

All work is on the `puzzle-pool` branch (worktree at `../h21-puzzle-pool`).

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

- Core implementation complete (db, llm, main.py, CLI tool)
- Not yet tested against live LLM -- need to run `h21-pool` to evaluate prompt quality
- Exhaustion detection logic in `_regenerate_pool()` (main.py) not yet implemented (only in CLI tool)
- No admin/control panel integration for viewing or managing the pool

## Open items

- Run `h21-pool` against live LLM to evaluate generation and validation prompt quality
- Tune batch generation prompt if needed based on evaluation results
- Add exhaustion detection to `_regenerate_pool()` in main.py (currently only the CLI tool has it)
- Consider admin panel integration for pool visibility
