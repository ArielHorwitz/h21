"""CLI tool for evaluating puzzle generation and validation prompts."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path
from typing import TextIO

from h21.config import load_config
from h21.db import VALID_DIFFICULTIES
from h21.llm import (
    LLMError,
    OpenAIClient,
    ValidationResult,
    generate_solution_batch,
    validate_solution_batch,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate puzzle generation and validation prompts",
    )
    parser.add_argument(
        "topic",
        help="Topic name to generate solutions for (e.g. 'Notable People')",
    )
    parser.add_argument(
        "--difficulty", default="normal", choices=sorted(VALID_DIFFICULTIES),
        help="Difficulty level (default: normal)",
    )
    parser.add_argument(
        "--count", type=int, default=100,
        help="Total number of solutions to generate (default: 100)",
    )
    parser.add_argument(
        "--batch-size", type=int, default=25,
        help="Solutions per LLM call (default: 25)",
    )
    parser.add_argument(
        "--exclude", "-e", type=str, default=None,
        help="File with solutions to exclude (one per line)",
    )
    parser.add_argument(
        "--output", "-o", type=str, default=None,
        help="Output file for accepted solutions (one per line)",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Show debug-level LLM logs",
    )
    args = parser.parse_args()

    if args.count < 1:
        parser.error("--count must be at least 1")
    if args.batch_size < 1:
        parser.error("--batch-size must be at least 1")

    log_level = logging.DEBUG if args.verbose else logging.WARNING
    logging.basicConfig(
        level=log_level,
        format="%(levelname)s [%(name)s] %(message)s",
        stream=sys.stderr,
    )

    # Load initial exclusion list from file.
    initial_exclusions: list[str] = []
    if args.exclude:
        exclude_path = Path(args.exclude)
        if not exclude_path.exists():
            print(f"Error: exclude file not found: {exclude_path}", file=sys.stderr)
            sys.exit(1)
        initial_exclusions = [
            line.strip() for line in exclude_path.read_text().splitlines()
            if line.strip()
        ]
        print(
            f"Loaded {len(initial_exclusions)} exclusions from {exclude_path}",
            file=sys.stderr,
        )

    config = load_config()
    client = OpenAIClient(
        config.openai_api_key,
        model=config.model,
        reasoning_effort=config.reasoning_effort,
    )

    try:
        kept, rejected = asyncio.run(_run(
            client=client,
            topic_name=args.topic,
            difficulty=args.difficulty,
            count=args.count,
            batch_size=args.batch_size,
            initial_exclusions=initial_exclusions,
        ))
    except LLMError as exc:
        print(f"LLM error: {exc}", file=sys.stderr)
        sys.exit(1)

    # Write accepted solutions to output file (one per line).
    if args.output and kept:
        output_path = Path(args.output)
        output_path.write_text("\n".join(kept) + "\n")
        print(f"Wrote {len(kept)} solutions to {output_path}", file=sys.stderr)

    # Print summary to stderr.
    _print_summary(kept, rejected)


async def _run(
    client: OpenAIClient,
    topic_name: str,
    difficulty: str,
    count: int,
    batch_size: int,
    initial_exclusions: list[str],
) -> tuple[list[str], list[ValidationResult]]:
    all_kept: list[str] = []
    all_rejected: list[ValidationResult] = []
    exclusion_list: list[str] = list(initial_exclusions)
    batch_number = 0
    consecutive_poor_batches = 0

    while len(all_kept) < count:
        batch_number += 1

        print(
            f"\n{'=' * 60}\n"
            f"Batch {batch_number}: requesting {batch_size} "
            f"({len(all_kept)}/{count} kept so far)\n"
            f"{'=' * 60}",
            file=sys.stderr,
        )

        batch = await generate_solution_batch(
            client,
            exclusion_list,
            topic_name,
            difficulty,
            batch_size=batch_size,
        )

        print(
            f"\n--- Generation response ({len(batch.solutions)} solutions) ---",
            file=sys.stderr,
        )
        print(batch.raw_response, file=sys.stderr)

        solutions = batch.solutions

        if not solutions:
            consecutive_poor_batches += 1
            if consecutive_poor_batches >= 2:
                print(
                    "\nTwo consecutive poor batches — topic may be exhausted",
                    file=sys.stderr,
                )
                break
            continue

        # Validate this batch.
        validation = await validate_solution_batch(
            client, solutions, exclusion_list, topic_name, difficulty,
        )

        print("\n--- Validation response ---", file=sys.stderr)
        print(validation.raw_response, file=sys.stderr)

        batch_kept = [r.solution for r in validation.results if r.kept]
        batch_rejected = [r for r in validation.results if not r.kept]
        batch_rejected_count = len(batch_rejected)
        all_rejected.extend(batch_rejected)

        print(
            f"\n    => {len(batch_kept)} kept, {batch_rejected_count} rejected",
            file=sys.stderr,
        )

        exclusion_list.extend(solutions)

        # Track exhaustion: if at least half the batch was rejected (or empty),
        # count it as a poor batch.
        if batch_rejected_count >= len(solutions) / 2:
            consecutive_poor_batches += 1
            if consecutive_poor_batches >= 2:
                print(
                    "\nTwo consecutive half-rejected batches — "
                    "topic may be exhausted at this difficulty",
                    file=sys.stderr,
                )
                if batch_kept:
                    all_kept.extend(batch_kept)
                break
        else:
            consecutive_poor_batches = 0

        all_kept.extend(batch_kept)

    return all_kept, all_rejected


def _print_summary(
    kept_solutions: list[str],
    rejected_solutions: list[ValidationResult],
) -> None:
    total = len(kept_solutions) + len(rejected_solutions)
    print(f"\n{'=' * 60}", file=sys.stderr)
    print("SUMMARY", file=sys.stderr)
    print(f"{'=' * 60}", file=sys.stderr)
    print(
        f"{len(kept_solutions)} kept, {len(rejected_solutions)} "
        f"rejected out of {total} generated",
        file=sys.stderr,
    )

    if kept_solutions:
        print(f"\nKEPT ({len(kept_solutions)}):", file=sys.stderr)
        for solution in kept_solutions:
            print(f"  {solution}", file=sys.stderr)

    if rejected_solutions:
        print(f"\nREJECTED ({len(rejected_solutions)}):", file=sys.stderr)
        for result in rejected_solutions:
            print(f"  {result.solution}  — {result.reason}", file=sys.stderr)
