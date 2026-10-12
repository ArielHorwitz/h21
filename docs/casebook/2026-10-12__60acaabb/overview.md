# Topic flow

## Scope

Everything about a topic's life: a player suggesting it, its puzzle pools being built, it being accepted or turned down, its pools refilling, and it eventually running dry. These items were spread across the puzzle pool case (c254) and the UI overhaul case (7563) and are consolidated here as one problem, since they interact (thresholds, quotas, what the player is told and when).

How it works today is described in the puzzle pool case and in `docs/architecture.md`: a new topic builds both difficulty pools in the background (one batch of 100 plus validation each), is turned down if either keeps fewer than 50, and refills in the background below 50; a refill keeping fewer than 10 stops further refills (an interim guard), and an empty pool makes the topic answer "run out of puzzles". Suggesting happens on the `/suggest` page.

## Open items

- **Expert threshold too strict.** Rebuilding the sandbox topics rejected "Movie Classics": normal kept 96, expert only 41 (World Geography expert kept 63). Options: a lower bar for expert, or judging new topics on normal only.
- **Running dry, properly.** Replace the interim guard with a real design, including a notice in the app that a topic has run dry, and possibly an earlier "running low" notice. Calibrate by running a few narrow topics until they genuinely run out (the batch-size runs suggest narrow topics hold roughly 100-150 normal subjects, a few months of puzzles).
- **Topic preview.** Players suggest names that mean more than they intend ("Disney" expecting films, getting theme parks and executives too). A preview before committing (how the topic will be read, a few sample subjects, sharper alternatives) would let them correct it without spending a suggestion. A static guide with example topics was tried on the Suggest page and dropped: the sweet spot is a topic with hundreds of well-known subjects ("Pop songs", not "Music" or "Classical composers"), and good examples proved hard to pick.
- **Remember rejected subjects.** Refills don't know what the validator rejected before, so they may propose it again. Storing rejections would sharpen exclusion lists.
- **Turned-down topics cost a suggestion.** A rejected topic still uses up one of the creator's daily suggestions.
- **Pool visibility** (low priority). The pool and refill tables can be queried from the control panel already; a dedicated view would mostly help debugging.
