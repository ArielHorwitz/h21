# Frontend

Vanilla JavaScript with no frameworks. All files in `static/`. Each page has its own HTML + JS file. API communication via `fetch`. No build step.

## App shell

Every page except login and the game shares a slim top bar (logo, help) and a
tab bar (Today, Friends, Profile). Their markup lives once in
`static/partials/top-bar.html` and `static/partials/tab-bar.html`, and
`render_page` in `main.py` substitutes them for the `<!--TOP_BAR-->` and
`<!--TAB_BAR-->` placeholders. The active tab comes from the page's
`<body data-tab="...">`, in CSS alone. On phones the tab bar sits at the
bottom; from 720px wide it moves into the top bar. `nav.js` swaps the Profile
tab's icon for the user's avatar. The game page has its own header (back,
topic, difficulty, Give up, answer meter) and a pinned composer instead.

Colors and sizes are CSS custom properties at the top of `style.css`. The
`[hidden]` attribute always wins over component `display` rules.

## Pages

| Page | Files | Description |
|------|-------|-------------|
| Today | `home.html`, `home.js` | Today's topics as compact rows with a button per offered series (color shows play state; finished series greyed out), notes for winding-down series, a New tag, friends who solved, and the topic's preview solutions behind its name. The user's own topics still being built appear too; polls while one is. Links to Suggest. |
| Suggest | `suggest.html`, `suggest.js` | The suggestion form with the remaining daily quota, tappable topic ideas, the user's topics with their previews and status, and recently turned-down topics. |
| Game | `index.html`, `game.js` | Gameplay: 21-segment answer meter, starter questions, answer chips with *Why?*, inline hints from one hint button, pinned composer, resume. Finished games go to the results page. |
| Results | `replay.html`, `replay.js` | Outcome, answer, meter and stats, Share / Leaderboard / More puzzles, then the question log with hints inline. Spoiler-gated for viewers who haven't played the puzzle. |
| Friends | `friends.html`, `friends.js` | Recent games with friends, search by name or player code, three suggestions (See all), links to Following and Followers with counts, and the anonymous-mode switch. |
| People | `people.html`, `people.js` | Following, Followers and Suggested lists as tabs: "Follows you" on people who follow back, Follow back for followers you don't follow, the full suggestions list. |
| Leaderboard | `leaderboard.html`, `leaderboard.js` | Ranked list for one puzzle with an Everyone / Friends switch. Redirects to Friends without query parameters. |
| Profile | `account.html`, `account.js` | Picture (AI generation flow), inline display name, stats, history list, settings (anonymous mode, control panel, log out). |
| Login | `login.html`, `login.js` | Log in / Join switch, invite request behind a link. `?invite=CODE` opens Join prefilled. |
| Help | `help.html` | Rules, answers, hints, sharing, topics, tips. |
| Control | `control.html`, `control.js` | Dev-only admin panel: SQL query tool, account management, invite management. |

`people-list.js` holds the person rows and follow/unfollow actions shared by Friends and People. `question-log.js` holds the question log rendering (entries, answer chips,
hints, the meter) shared by the game and results pages.

## Game State Flow

1. `game.js` reads `topic` and `difficulty` from URL query params (e.g. `/game?topic=western-history&difficulty=normal`)
2. On init, calls `GET /api/game/existing` to check for an in-progress or completed game for today's puzzle
3. If a game exists, replays all recorded questions to restore UI state (counter, log, hints)
4. If no game exists, calls `POST /api/game/new` to start a fresh game (which triggers solution generation on the backend if needed)
5. Each question submission calls `POST /api/ask` with the `game_id` and `question_number`
6. Hints unlock every 4 questions. The hint button reveals the next one via `POST /api/hint`, and it appears in the log
7. Game ends on "win" answer or after 21 questions. Calls `POST /api/game/end`, then moves to the results page

## JS Patterns

- No module system — scripts loaded via `<script>` tags
- DOM elements grabbed by ID at the top of each file
- State tracked in module-level variables (`questionsAsked`, `gameId`, `gameFinished`, etc.)
- `localStorage` used to persist `user_id` across sessions
- All API calls use `fetch` with JSON bodies and manual error handling
- Share functionality copies a text summary with emoji answer grid to clipboard

## Styling

- Single `style.css` file for all pages
- No CSS framework or preprocessor
