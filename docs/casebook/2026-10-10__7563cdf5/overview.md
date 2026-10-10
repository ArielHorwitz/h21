# Relaunch UI/UX overhaul

## Goal

A major pass over the whole app's UI and UX for the clean relaunch (see the puzzle pool case, c254, for the relaunch context). Keep the brand assets and the palette; everything else (layout, buttons, navigation, in-app hints) is open to reconsideration. Mobile first: most play happens on phones.

Work happens on the `ui-pass` branch, based on `dev`.

## Audit of the old UI (2026-10-10)

Screenshots of every page at phone (390px) and desktop widths, on a seeded sandbox.

- **Home buried the main action.** Today's puzzles sat about three phone screens down, below three recent-results cards and "People You May Know". Difficulty buttons were small ghost buttons with weak played/in-progress states, and friend activity was a cryptic "Normal:" avatar row.
- **The big logo on every page** used about a third of a phone screen, with nav icons crammed against it.
- **Game screen:** empty on start with no guidance, five locked hint rows above the conversation, Give up as prominent as Ask, explanations not reachable.
- **Account page did everything:** profile, player code, anonymous toggle, friends management, a cramped ISO-date history table, and mismatched Control Panel / Log out / Back buttons.
- **Smaller:** `/leaderboard` errors without query parameters, login stacks three forms, a niche "Replay a Game" ID box on home, topic suggestions don't show the daily quota.

## Decisions

- **Navigation: both a slim branded top bar and a bottom tab bar.** The top bar keeps the logo visible on every page (branding and a sense of place, which the user values); the tabs (Today, Friends, Profile) carry navigation. On wide screens (720px+) the tabs move into the top bar. The game screen replaces both with its own header (back arrow plus the logo mark, topic, difficulty, Give up), since the composer needs the bottom.
- **Shared chrome is included server-side.** `render_page` replaces `<!--TOP_BAR-->` and `<!--TAB_BAR-->` with `static/partials/*.html`, so there is one copy and no flash. The active tab is pure CSS from `<body data-tab="...">`.
- **Home is "Today" only:** topic cards with two large difficulty tiles showing Play / "Continue · N questions" / "Solved in N" / "Not solved", plus avatars of friends who played. Topic suggestion is collapsed behind a button and shows the remaining daily quota. The replay-by-ID box is gone.
- **New Friends page** (`/friends`) takes recent results and friend suggestions off home.
- **Game:** a 21-segment meter colored by answer, a starter card with tappable example questions, answer chips with a "Why?" toggle for the explanation, revealed hints inline in the log (resumed games place them after the question they followed), one hint button in the composer, and the pending answer shown as the animated brand mark.
- Design tokens (CSS custom properties) introduced from the existing palette; a global `[hidden] { display: none !important }` so component display rules can't override `hidden`.

## Status

- Phase 1 done: shell, Today, Friends, game.
- Not yet redesigned (still old look): account/profile, login, help, leaderboard, replay/results, control panel.

## Open items

- Redesign the remaining pages; move friend management from account to Friends.
- Results page after a game (currently the old replay page, which is a jarring transition).
- `/leaderboard` with no parameters should be a useful page, not an error.
- Starter questions are generic ("Is it a person?" reads oddly for World Geography). Consider topic-aware starters.
- Not yet checked on a real phone: the pinned composer with the on-screen keyboard, and iPhone safe areas.
- Clean up CSS left unused by the old home and game layouts once all pages are migrated.
