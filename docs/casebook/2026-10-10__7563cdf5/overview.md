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

## Later decisions

- **Compact topic rows** (after user feedback that the tiles were too tall and "Play" was redundant): one row per topic, name and friends who played on the left, Normal/Expert buttons on the right whose look carries the state (gold outline: unplayed; filled gold "Q6": in progress; green "✓ 12": solved; muted "✗": not solved).
- **Results page** leads with outcome, the answer, the answer meter and stats, then Share / Leaderboard / More puzzles, then the log with revealed hints inline and unused hints collapsed. Share uses the native share sheet when available and links to the results page (spoiler-gated) instead of quoting a game ID, so the home page's replay-by-ID box isn't needed.
- **Profile vs Friends split.** Profile is about you: picture, inline-editable display name, stats (played, solved %, average questions on wins), tappable history, settings (anonymous mode, control panel, log out). Friends holds all social features: recent games, one search box for names and player codes (search now matches exact codes), suggestions, following with unfollow.
- **Login** is one card with a Log in / Join switch, invite requests behind a link, and `?invite=CODE` prefilling Join so invites can be shared as links.
- **Help** rewritten for the new UI and inlined (`help-content.html` removed). **Leaderboard** is a ranked list with an Everyone / Friends switch, and `/leaderboard` without a puzzle redirects to Friends. The **control panel** only moved into the shell.
- `question-log.js` shares log rendering between the game and results pages. Dead CSS from the old layouts was swept (about 740 lines).

## Status

- All pages redesigned.

## Open items

- Starter questions are generic ("Is it a person?" reads oddly for World Geography). Consider topic-aware starters.
- Not yet checked on a real phone: the pinned composer with the on-screen keyboard, and iPhone safe areas.
- Leaderboard and results show usernames for other players where display names would read better (the replay API only returns `username`).
- The control panel's internals still use the old styling.
