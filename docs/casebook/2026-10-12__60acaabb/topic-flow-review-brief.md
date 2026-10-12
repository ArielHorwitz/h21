# Brief: review the topic flow of H21

You are reviewing one part of a small web game and writing a recommendation report. Work only from the code in this directory, what you can reason out, and the facts below. Do not implement anything and do not modify the code.

## The game

H21 is a daily 21-questions game. Each topic has two puzzles a day (normal and expert difficulty): a secret subject drawn from that topic, which players identify by asking an AI host yes/no questions. Players can also suggest new topics. The audience is small (friends and family) and mostly plays on phones. The stack is Python/FastAPI, SQLite, vanilla JS, and OpenAI models. Start from `.claude/CLAUDE.md` and `docs/` for orientation; the relevant code is mostly in `src/h21/main.py` (topic creation, pool refills, drawing puzzles), `src/h21/db.py`, `src/h21/llm.py` (generation and validation prompts) and `static/suggest.*` / `static/home.*`.

## What "topic flow" covers

Everything about a topic's life: a player suggesting it, the system building its puzzles, the topic being accepted or turned down, its puzzles being replenished over time, and a topic eventually running out of subjects. Consider it from the player's side (what they see, decide and understand) and the system's side (cost, reliability, quality of puzzles).

## Observed facts

- Players sometimes suggest a name that covers more than they intend. Example: someone suggested "Disney" expecting puzzles about the films, and got puzzles about theme parks, executives and company history as well.
- A topic is turned down if either difficulty keeps fewer than 50 subjects after its first batch. "Movie Classics" was turned down: normal kept 96 subjects, expert kept 41. "World Geography" expert kept 63.
- In generation experiments, the share of generated subjects the validator rejects climbs as a topic's list of already-used subjects grows past roughly 100. Narrow topics appeared to hold roughly 100 to 150 normal-difficulty subjects, a few months of daily puzzles. Broad topics (notable people, world geography) showed little rejection even past 200.
- When a pool runs low it refills in the background. If a refill keeps fewer than 10 subjects, no further refills happen, and when the pool empties the topic responds that it has run out of puzzles. Nothing in the app tells players about this in advance.
- Subjects the validator rejects are not stored, so later refills may propose them again.
- A topic that is turned down still uses up one of the creator's daily topic suggestions (default 3 a day).
- Building a new topic takes about a minute; the creator sees a "creating" state meanwhile.
- Model costs are low (cents per topic build), but they are paid by the person running the game.

## Your task

1. Map the current topic flow end to end, briefly.
2. Identify the problems and risks, including any not listed above. For each, say who it affects and how badly.
3. Recommend changes. For each: what to do, why, trade-offs, rough effort, and priority. Where there are real alternatives, lay them out and say which you'd pick and why.
4. Note anything you'd want measured or tested before deciding.

Be concrete and opinionated; it's fine to recommend doing nothing about something. Write the report to `REPORT.md` in this directory (Markdown, no length limit, but put a short summary of your top recommendations first).
