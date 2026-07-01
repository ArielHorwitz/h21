# Frontend

Vanilla JavaScript with no frameworks. All files in `static/`. Each page has its own HTML + JS file. API communication via `fetch`. No build step.

## Pages

| Page | Files | Description |
|------|-------|-------------|
| Home | `home.html`, `home.js` | Topic list with difficulty buttons. Topic suggestion form. Entry point to games. |
| Game | `index.html`, `game.js` | Main gameplay. Q&A loop, hint panel, share button, game resume. |
| Login | `login.html`, `login.js` | Registration (with invite code) and login forms. |
| Account | `account.html`, `account.js` | User profile, daily usage stats. |
| Control | `control.html`, `control.js` | Dev-only admin panel: SQL query tool, account management, invite management. |
| Help | `help.html`, `help-content.html` | Game rules and instructions. |

## Game State Flow

1. `game.js` reads `topic` and `difficulty` from URL query params (e.g. `/game?topic=western-history&difficulty=medium`)
2. On init, calls `GET /api/game/existing` to check for an in-progress or completed game for today's puzzle
3. If a game exists, replays all recorded questions to restore UI state (counter, log, hints)
4. If no game exists, calls `POST /api/game/new` to start a fresh game (which triggers solution generation on the backend if needed)
5. Each question submission calls `POST /api/ask` with the `game_id` and `question_number`
6. Hints unlock every 4 questions. Player must reveal them sequentially via `POST /api/hint`
7. Game ends on "win" answer or after 21 questions. Calls `POST /api/game/end` which returns the solution and all hints

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
