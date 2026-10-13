# Relaunch UX overhaul

## Goal

Widened on 2026-10-12 from a UI pass to the whole user experience, including playtesting fixes and blind UX reviews.

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
- **Results page** leads with outcome, the answer, the answer meter and stats, then Share / Leaderboard / More puzzles, then the log with revealed hints inline and unused hints collapsed. Share keeps the Wordle-style emoji teaser (one colored dot per answer, a bulb per hint) and passes that text, plus a link, to the native share sheet when available (clipboard otherwise); the link goes to the results page (spoiler-gated) instead of quoting a game ID, so the home page's replay-by-ID box isn't needed.
- **Profile vs Friends split.** Profile is about you: picture, inline-editable display name, stats (played, solved %, average questions on wins), tappable history, settings (anonymous mode, control panel, log out). Friends holds all social features: recent games, one search box for names and player codes (search now matches exact codes), suggestions, following with unfollow.
- **Login** is one card with a Log in / Join switch, invite requests behind a link, and `?invite=CODE` prefilling Join so invites can be shared as links.
- **Help** rewritten for the new UI and inlined (`help-content.html` removed). **Leaderboard** is a ranked list with an Everyone / Friends switch, and `/leaderboard` without a puzzle redirects to Friends. The **control panel** is split into tabs (Invites, Users, Activity, Query, Logs; remembered in the URL hash) and restyled with the shared inputs, buttons and a `data-table` component.
- `question-log.js` shares log rendering between the game and results pages. Dead CSS from the old layouts was swept (about 740 lines).

- **Unsolved games are private.** Failed and abandoned games are the same thing, "not solved", and are never shown to anyone else: leaderboards and recent games list solvers only (as originally designed), and the friend avatars on Today show friends who *solved* the puzzle ("solved", not "played"). A brief experiment showing a "Didn't solve" group on leaderboards was reverted: leaderboards are global (all non-anonymous solvers, with a Friends filter, per the social features case), so it advertised strangers' failures, which isn't the engagement we want. You still see your own: red on Today, ✗ in history (for failed and abandoned alike), "Not this time" on the results page, and both count as unsolved in your stats.
- **Today's buttons are color-only** (user preference for a clean, aligned look): outline for unplayed, filled gold in progress, filled green solved, filled red not solved. Details are in the button's tooltip and accessible label.
- **Unfinished games from past days open on the results page**, reading like a failed game, with the answer revealed since the puzzle's day is over.
- **The sandbox covers every state on purpose:** dev has a solved, an unsolved and an in-progress puzzle today with the rest unplayed, an abandoned game earlier in the week, and a turned-down topic; friends are mid-game today and didn't solve puzzles dev solved today and yesterday (tests check these stay out of social views).

- **Partially vs Depends redefined in the host prompt** (they overlapped: "partly correct or context-dependent" vs "varies based on interpretation"). Partially: the question is clear but the true answer is mixed (true for part of the subject or to some degree). Depends: the question can't be answered as asked (interpretation, context left open, or not answerable as true/false). Tie-break given to the model: if a more precise question would still be mixed, partially; if it would be a clean yes/no, depends. Help describes each with what to try next and no longer implies either means "close". Checked on 20 borderline questions x 3 runs with `gpt-6-luna`/medium: 51/60 answers as expected vs 38/60 with the old prompt. Depends cases are now unanimous (old prompt answered "Is it old?" for the telephone "yes" and mixed partially/depends for "Was he successful?" for Napoleon). Mixed-nationality questions (Einstein "American?", Curie "French?") still waver between yes and partially, which is arguably defensible.
- **Answer explanations stay hidden until the game ends** (each is effectively a hint): not returned by the ask endpoint, stripped from in-progress games, no Why? in the game screen; shown on the results page.
- Partially shares Depends' blue (chips, meter, share emoji), and the hint button moved to the left of the composer, away from send.

- **Generated avatars: style and background instead of adjectives.** The old prompt ("visually striking... Colorful, bold" plus a random adjective, many of them glow words like holographic or iridescent) produced a samey neon magenta/cyan look. Now each avatar gets a random noun, one of 7 styles (linocut, stained glass, pixel art, embroidered patch, origami, mosaic, rubber-hose cartoon) and two random background colors from 12, with the model told to use whichever contrasts better with the subject. Reference photos get a random style only, leaving the background to the photo; typed prompts are sent as written. Model: `gpt-image-2.5-flare` at low quality (about $0.006 per image).
  - How we got there, in four rounds of contact sheets: (1) 20 styles on one noun showed the neon was gone but everything landed on cream, since "plain background" defaults to cream; (2) 12 styles x 4 nouns with the two-color background fixed that, Flare picking the contrasting color more reliably than mini; (3) quality made no visible difference at avatar size on either model, and Flare's default ("auto") had been low all along; (4) 7 styles x 10 nouns x 2 runs on both models at low quality: Flare reads more clearly at small sizes, mini has more texture and character and draws side angles. Flare repeats itself more (same background in 56/70 run pairs vs 40/70) but its repeats still differ visibly. The user chose Flare low.
  - Costs per image as measured: mini high (the old default) $0.033, mini low $0.002, Flare low $0.006, Flare high $0.053.
  - Considered and set aside: assigning curated palettes (dropping color words was simpler), and a style picker on the profile page (a possible follow-up).

- **Suggesting a topic has its own page** (`/suggest`; Today links to it): the form with the quota pill, and "Your topics" (ready ones link to play, creating ones show progress, turned-down ones show the reason and Dismiss). A guide with broad-vs-focused example topics was tried and dropped: good examples are hard to pick, since the sweet spot is a topic with hundreds of well-known subjects ("Pop songs", not "Music" or "Classical composers"), and the user wasn't satisfied with any set. The motivating problem remains (players suggest "Disney" expecting films and get theme parks and executives too). Considered for later: a preview step showing how a topic will be read (scope, sample subjects, sharper alternatives) before it uses up a suggestion.
- **Quotas are accented pills** ("3 pictures left this month", "3 topic suggestions left today"), red when used up; remaining picture generations also show on the avatar preview.
- **The results log ends with how the game ended**, when it wasn't a solve: "Gave up after question N", "Out of questions", "Left unfinished" (past day) or "Still in progress" (today), as a dashed closing entry, in keeping with hints shown where they were revealed.
- **Results actions trimmed to one row:** Share result, then Leaderboard, both gold outlines; More puzzles was dropped as redundant with the tab bar (it pushed the buttons onto a second row). Renaming the Today tab to Puzzles was discussed and left as Today for the daily-ritual feel.
- **Two button styles:** filled gold for the main action, gold outline for the rest (the muted grey outline is gone). Danger buttons, text links and segmented switches keep their own looks.

## Status

- All pages redesigned.

## Blind reviews (planned)

- **Topic flow:** two independent agents (Opus 5.5 and GPT-6.1 Sol), the same neutral brief (current behavior and observed problems as facts, none of our ideas), code without the casebook. Their reports are synthesized into one recommendation report for the user to review before anything is changed. The topic flow case (60ac) holds the work that follows.
- **Whole-app UX:** eight blind agents on regular-user features only (no admin), each running its own local sandbox and driving it at phone size: two starting points (a brand-new player, and a returning regular with friends and history), four models each (Opus, Sonnet, Sol, Terra). Synthesized into one report for the user to review before addressing. Fable and Astra are not used.

## Open items

- **For the relaunch session: open registration.** Today the app is invite-only, to keep strangers from running up the API bill. With spending capped by the API limit, the user wants strangers to be able to register without an invite (sending people a link without a code is an unpleasant start), throttled to about three new registrations a day, with a way to switch it off if it gets abused. Not part of this session.

- Real-phone check done on Android; there won't be an iPhone check.
- No avatar style picker.
- Stats (including per-puzzle solve rates) are out of scope.
- The game model default is now `gpt-6-luna` at high effort; the code default was `gpt-5.4-nano` at high, and production's config sets `gpt-5.4-mini` at high. The concern was date-reasoning mistakes seen in the past (e.g. treating 1400 as before year 1): on 20 date and ordering traps x 3 runs, luna got 60/60 at both medium and high, with no latency difference (median about 2.4s). High costs about 20 more reasoning tokens per answer, roughly $0.00013 vs $0.00012 per question at luna's $0.10/$0.50 per million tokens, so high was chosen for the margin.
- Topic-related items live in the topic flow case (60ac). Deployment and the relaunch cutover will be overhauled in a separate session, after the topic flow work and a several-day playtest.
