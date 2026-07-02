# H21 — Social Comparison & Daily Recap

*A user-perspective design summary*

## Background: Why Not a Leaderboard?

A leaderboard was one of the most requested features, but on closer inspection it doesn't fit H21 well. The player base is small (roughly ten players, likely never more than a few dozen) and made up mostly of friends and family. Several structural issues made a traditional leaderboard a poor fit:

- **Fragmentation.** Topics are user-generated, and each is played across multiple difficulty levels. With dozens of topics and several difficulties, the game quickly splinters into a huge number of possible leaderboards — most of them empty or dominated by a single player. Almost every player would end up looking at a different, mostly barren board.
- **Gaming the system.** Because anyone can create a topic, a player could generate deliberately narrow, easy topics (e.g. "pop singers active in 2001") that are trivially solvable, then farm wins to dominate a global ranking.
- **Incomparable metrics.** Wins alone don't capture what players actually care about — solving in the fewest questions. And hints (which are optional and vary in number) make direct comparison murky: is 10 questions with 2 hints better or worse than 7 questions with 1 hint?

Rather than force-fit a leaderboard, we pivoted to **direct, contextual comparison** built around the games players actually played.

---

## What We Settled On

### The Daily Recap

When a player opens the app, they see a **recap of yesterday's games**. Yesterday (not today) is the anchor because everyone gets the same experience regardless of when they played — no asymmetry between the first friend to play and the last. It creates a shared morning moment: everyone checks the recap, and it becomes a natural conversation starter ("you beat me by two questions yesterday!").

For **each game the player played yesterday**, the recap shows:

- The **topic**, **difficulty**, and **date**.
- Up to **three friends** who played that same game:
  - the **top performer**, and
  - the **two friends whose scores were closest** to the player's own.

This keeps the recap bite-sized. A typical player plays two or three games a day (up to about five), so the recap stays short and scannable — just enough social spark without overwhelming. Showing only the top performer plus near-neighbors means the recap is motivating for everyone, not just whoever came first.

Comparisons only include friends who have their games set to shareable (a preferences toggle, handled separately from this feature).

### The Comparison Page

Each game in the recap links to a **dedicated comparison page** for that game, where a curious player can dig deeper: see **all** their friends who played it, sorted by performance, with **question count and hint count both visible** so the ranking is transparent.

### How Performance Is Ranked

Players are sorted by a simple, consistent rule that handles the hint problem cleanly:

- Ranking is driven by **number of questions**, with each hint applying a large penalty (effectively bumping a player into a worse tier).
- The practical effect: **anyone who used fewer hints always ranks above anyone who used more**, regardless of question count. Someone with zero hints beats anyone with one hint; one hint beats two; and so on. Within the same hint count, fewer questions wins.
- Players **never see a raw score** — only their **question count** and **hint count**. The penalty is purely an internal sorting mechanism, so it can be tuned later without affecting anything players see or any historical data.

This makes hints a clear, understood trade-off: using them is fine and still lets you enjoy and finish the game, but opting to play hint-free earns you bragging rights. It's self-selecting — competitive friends play clean, casual players use hints freely — with no artificial "one hint = X questions" formula shown to anyone.

### Friends

The feature depends on a lightweight **friends system**: players choose who their friends are, i.e. whose results they want to see comparisons against. All comparison surfaces (recap and comparison pages) draw from this friend set, filtered to those who've made their games shareable.

---

## Why This Works

- **No fragmentation** — comparison happens on the specific games you played, not across dozens of sparse leaderboards.
- **No incentive to game the system** — there's no global ranking to farm, and an easy self-made topic just shows up as "solved in three questions," visible to all.
- **Fair and transparent** — everyone sees the same yesterday's recap, and rankings show the actual question and hint counts behind them.
- **Social, not aggressive** — it's about "how did I stack up against my friends," not chasing an abstract rank. It fits a tight-knit group and encourages continued play through friendly rivalry.

---

## Deferred Ideas (For Future Iteration)

These came up in brainstorming and were intentionally set aside. The plan is to ship the recap first, watch how people actually use it, and let real behavior guide what comes next.

### Live "today" comparison
In addition to yesterday's recap, show today's games live — when you finish a game, immediately see which friends have already played it and how you compare. This gives instant feedback ("I beat my mate!") but is asymmetric (the first friend to play sees nothing). Considered worthwhile but not yet decided; yesterday's recap comes first.

### Friend-driven game discovery
A separate "friends also played these" section in the recap, surfacing games your friends played that you haven't tried yet. This nudges players toward a shared pool of games — more play, more comparison data, more fun feedback for everyone. Should be kept unobtrusive (a small list of three or four), not a pushy recommendation engine.

### Deeper comparison directions
Richer views to explore once the basics are live:

- **Personal trajectory** — track improvement on a given topic over time ("twelve questions last week, nine now").
- **Head-to-head rivalry** — your overall record against a specific friend across all games, including "nemesis" topics.
- **Skill profiles / patterns** — which topics each player dominates and which are their weak spots.
- **Category-based recognition** — multiple ways to stand out (best on expert difficulty, most improved, most consistent) rather than one global ranking.

---

*Next step: build and ship yesterday's recap, then iterate based on how players actually engage with it.*